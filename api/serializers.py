from rest_framework import serializers
from .models import User, Workspace, WorkspaceMember, Document, DocumentVersion, Comment, Tag, AuditLog


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'created_at']

    def validate_email(self, value):
        if '@' not in value:
            raise serializers.ValidationError('Enter a valid email address.')
        return value


class WorkspaceSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Workspace
        fields = ['id', 'name', 'owner', 'is_active', 'created_at', 'member_count']


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceMember
        fields = ['id', 'workspace', 'user', 'user_display', 'role', 'joined_at']
        validators = []  # disable DRF's auto unique-together validator so the DB's
                          # IntegrityError is what triggers, letting the view map it to 409

    def get_user_display(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'title', 'content', 'workspace', 'created_by', 'status', 'updated_at']

    def validate_status(self, value):
        valid_statuses = [choice[0] for choice in Document.Status.choices]
        if value not in valid_statuses:
            raise serializers.ValidationError(f'Status must be one of {valid_statuses}')
        return value


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = ['id', 'document', 'content', 'version_number', 'saved_by', 'saved_at']


class CommentSerializer(serializers.ModelSerializer):
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['id', 'document', 'author', 'content', 'parent', 'created_at', 'reply_count']

    def get_reply_count(self, obj):
        return obj.replies.count()

    def validate(self, data):
        parent = data.get('parent')
        document = data.get('document')
        if parent and parent.document_id != document.id:
            raise serializers.ValidationError('A reply must belong to the same document as its parent comment.')
        return data


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'action', 'model_name', 'object_id', 'timestamp']