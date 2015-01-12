from __future__ import absolute_import, unicode_literals

from chatpro.rooms.models import Room
from chatpro.utils.temba import ChangeType
from dash.orgs.models import Org
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import ugettext_lazy as _
from temba.types import Contact as TembaContact
from uuid import uuid4
from .tasks import push_contact_change


class Contact(models.Model):
    """
    Corresponds to a RapidPro contact who is tied to a single room
    """
    uuid = models.CharField(max_length=36, unique=True)

    org = models.ForeignKey(Org, verbose_name=_("Organization"), related_name='contacts')

    room = models.ForeignKey(Room, verbose_name=_("Room"), related_name='contacts',
                             help_text=_("Room which this contact belongs in"))

    urn = models.CharField(verbose_name=_("URN"), max_length=255)

    is_active = models.BooleanField(default=True, help_text=_("Whether this contact is active"))

    created_by = models.ForeignKey(User, null=True, related_name="contact_creations",
                                   help_text="The user which originally created this item")
    created_on = models.DateTimeField(auto_now_add=True,
                                      help_text="When this item was originally created")

    modified_by = models.ForeignKey(User, null=True, related_name="contact_modifications",
                                    help_text="The user which last modified this item")
    modified_on = models.DateTimeField(auto_now=True,
                                       help_text="When this item was last modified")

    @classmethod
    def create(cls, org, user, full_name, chat_name, urn, room, uuid=None):
        if org.id != room.org_id:  # pragma: no cover
            raise ValueError("Room does not belong to org")

        # if we don't have a UUID, then we created this contact
        if not uuid:
            do_push = True
            uuid = unicode(uuid4())
        else:
            do_push = False

        # create contact
        contact = cls.objects.create(org=org, urn=urn, room=room, uuid=uuid,
                                     created_by=user, modified_by=user)

        # add profile
        Profile.objects.create(contact=contact, full_name=full_name, chat_name=chat_name)

        if do_push:
            contact.push(ChangeType.created)

        return contact

    @classmethod
    def from_temba(cls, org, room, temba_contact):
        full_name = temba_contact.name
        chat_name = temba_contact.fields.get(org.get_chat_name_field(), None)
        urn = temba_contact.urns[0]
        return cls.create(org, None, full_name, chat_name, urn, room, temba_contact.uuid)

    def update_from_temba(self, org, room, temba_contact):
        self.profile.full_name = temba_contact.name
        self.profile.chat_name = temba_contact.fields.get(org.get_chat_name_field(), None)
        self.profile.save()

        self.is_active = True
        self.urn = temba_contact.urns[0]
        self.room = room
        self.save()

    def as_temba(self):
        temba_contact = TembaContact()
        temba_contact.name = self.profile.full_name
        temba_contact.urns = [self.urn]
        temba_contact.fields = {self.org.get_chat_name_field(): self.profile.chat_name}
        temba_contact.groups = [self.room.uuid]
        temba_contact.uuid = self.uuid
        return temba_contact

    def push(self, change_type):
        push_contact_change.delay(self.id, change_type)

    def get_urn(self):
        return tuple(self.urn.split(':', 1))

    def release(self):
        self.is_active = False
        self.save()
        self.push(ChangeType.deleted)


class Profile(models.Model):
    """
    A user or contact who can participate in chat rooms
    """
    user = models.OneToOneField(User, null=True)

    contact = models.OneToOneField(Contact, null=True)

    full_name = models.CharField(verbose_name=_("Full name"), max_length=128, null=True)

    chat_name = models.CharField(verbose_name=_("Chat name"), max_length=16, null=True,
                                 help_text=_("Shorter name used for chat messages"))

    def is_contact(self):
        return bool(self.contact_id)

    def is_user(self):
        return bool(self.user_id)

    def as_json(self):
        _type = 'C' if self.is_contact() else 'U'

        return dict(id=self.id, type=_type, full_name=self.full_name, chat_name=self.chat_name)

    def __unicode__(self):
        if self.full_name:
            return self.full_name
        elif self.chat_name:
            return self.chat_name
        elif self.is_contact():
            return self.contact.get_urn()[1]
        else:
            return self.user.email
