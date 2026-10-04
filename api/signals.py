from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Document, AuditLog


@receiver(post_save, sender=Document)
def log_document_activity(sender, instance, created, **kwargs):
    AuditLog.objects.create(
        actor=instance.created_by,
        action='created' if created else 'updated',
        model_name='Document',
        object_id=str(instance.id),
    )