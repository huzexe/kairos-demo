from django.utils import timezone

from .models import FollowUp


def follow_up_counts(request):
    """Number of follow-ups due today or overdue, for the sidebar badge."""
    if not request.user.is_authenticated:
        return {}
    due = FollowUp.objects.filter(done_at__isnull=True, due_date__lte=timezone.localdate()).count()
    return {"follow_ups_due": due}
