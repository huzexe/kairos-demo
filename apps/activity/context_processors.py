from django.utils import timezone

from .services import open_follow_ups


def follow_up_counts(request):
    """Number of follow-ups due today or overdue, for the sidebar badge."""
    if not request.user.is_authenticated:
        return {}
    due = open_follow_ups().filter(due_date__lte=timezone.localdate()).count()
    return {"follow_ups_due": due}
