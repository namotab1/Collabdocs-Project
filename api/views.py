from django.shortcuts import render

# Create your views here.
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import User, Workspace, WorkspaceMember, Document, DocumentVersion, Comment, Tag, AuditLog
from .serializers import (
    UserSerializer, WorkspaceSerializer, WorkspaceMemberSerializer,
    DocumentSerializer, DocumentVersionSerializer, CommentSerializer,
    TagSerializer, AuditLogSerializer
)


class UserViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.select_related('owner').annotate(
            member_count=Count('members', distinct=True)
    )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            workspace = serializer.save()
            WorkspaceMember.objects.create(
                workspace=workspace,
                user=workspace.owner,
                role=WorkspaceMember.Role.ADMIN,
            )

        return Response(self.get_serializer(workspace).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'])
    def members(self, request, pk=None):
        workspace = self.get_object()

        if request.method == 'POST':
            data = request.data.copy()
            data['workspace'] = str(workspace.id)
            serializer = WorkspaceMemberSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            try:
                member = serializer.save()
            except IntegrityError:
                return Response(
                    {'error': 'This user is already a member of this workspace.'},
                    status=status.HTTP_409_CONFLICT
                )
            return Response(WorkspaceMemberSerializer(member).data, status=status.HTTP_201_CREATED)

        # GET
        members = WorkspaceMember.objects.filter(workspace=workspace).select_related('user')
        return Response(WorkspaceMemberSerializer(members, many=True).data)

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        workspace = Workspace.objects.filter(pk=pk).annotate(
            doc_count=Count('documents', distinct=True),
            member_count=Count('members', distinct=True),
            comment_count=Count('documents__comments', distinct=True),
        ).first()

        if not workspace:
            return Response({'error': 'Workspace not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'workspace_id': str(workspace.id),
            'name': workspace.name,
            'document_count': workspace.doc_count,
            'member_count': workspace.member_count,
            'total_comments': workspace.comment_count,
        })


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        queryset = Document.objects.select_related('workspace', 'created_by')

        workspace_id = self.request.query_params.get('workspace')
        status_param = self.request.query_params.get('status')
        tag_name = self.request.query_params.get('tag')
        search = self.request.query_params.get('search')

        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if tag_name:
            queryset = queryset.filter(tags__name=tag_name)
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(content__icontains=search))

        return queryset.distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            document = serializer.save()
            DocumentVersion.objects.create(
                document=document,
                content=document.content,
                version_number=1,
                saved_by_id=document.created_by_id,
            )

        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            document = serializer.save()
            next_version = document.versions.count() + 1
            DocumentVersion.objects.create(
                document=document,
                content=document.content,
                version_number=next_version,
                saved_by_id=request.data.get('created_by', document.created_by_id),
            )

        return Response(self.get_serializer(document).data)

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        document = self.get_object()
        versions = document.versions.all().order_by('version_number')
        return Response(DocumentVersionSerializer(versions, many=True).data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        document = self.get_object()

        version_agg = document.versions.aggregate(version_count=Count('id'))
        comment_agg = document.comments.aggregate(comment_count=Count('id'))
        contributor_count = document.versions.values('saved_by').distinct().count()

        return Response({
            'document_id': str(document.id),
            'version_count': version_agg['version_count'],
            'comment_count': comment_agg['comment_count'],
            'contributor_count': contributor_count,
    })

    @action(detail=True, methods=['post'])
    def tags(self, request, pk=None):
        document = self.get_object()
        tag_names = request.data.get('tags', [])

        if not tag_names:
            return Response({'error': 'tags list is required'}, status=status.HTTP_400_BAD_REQUEST)

        added = []
        for name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=name)
            tag.documents.add(document)
            added.append(name)

        return Response({'document_id': str(document.id), 'tags_added': added}, status=status.HTTP_200_OK)


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer

    def get_queryset(self):
        queryset = Comment.objects.select_related('document', 'author', 'parent')
        document_id = self.request.query_params.get('document')
        if document_id:
            queryset = queryset.filter(document_id=document_id)
        return queryset


class TagViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class AuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        queryset = AuditLog.objects.select_related('actor')

        actor_id = self.request.query_params.get('actor')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if actor_id:
            queryset = queryset.filter(actor_id=actor_id)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)

        return queryset