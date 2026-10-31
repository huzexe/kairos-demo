from django.core.exceptions import ValidationError
from django.db import transaction

from apps.pipeline import services as pipeline_services
from apps.pipeline.models import Lead, Stage

from .models import Client, Contact


@transaction.atomic
def convert_lead(lead: Lead, client: Client, user=None) -> Client:
    """
    Turn a won lead into a client.

    `client` is an unsaved Client filled in from the conversion form. The
    lead is moved to Won (if it isn't already), its contact person becomes
    the client's main contact, and the lead's timeline stays visible on the
    client's page.
    """
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if Client.objects.filter(lead=lead).exists():
        raise ValidationError("This lead is already a client.")

    if lead.stage != Stage.WON:
        pipeline_services.move_lead(lead, Stage.WON, user=user)
        lead.refresh_from_db()

    client.lead = lead
    client.created_by = user
    if not client.instagram and lead.instagram:
        client.instagram = lead.instagram
    if not client.notes and lead.notes:
        client.notes = lead.notes
    client.full_clean()
    client.save()

    Contact.objects.create(
        client=client, name=lead.name, phone=lead.phone, email=lead.email, is_primary=True,
    )
    return client


def set_primary_contact(contact: Contact) -> None:
    """Make one contact the main one; the others stop being main."""
    with transaction.atomic():
        Contact.objects.filter(client=contact.client).exclude(pk=contact.pk).update(is_primary=False)
        if not contact.is_primary:
            contact.is_primary = True
            contact.save(update_fields=["is_primary"])
