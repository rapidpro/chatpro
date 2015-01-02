from __future__ import unicode_literals

from chatpro.rooms.models import Room
from dash.orgs.models import Org
from django.conf import settings
from django.contrib.auth.models import User
from temba import TembaClient
from .models import Profile


######################### Monkey patching for the User class #########################

def _user_get_all_rooms(user):
    if not hasattr(user, '_rooms'):
        # org admins have implicit access to all rooms
        if user.is_administrator():
            user._rooms = Room.get_all(user.get_org())
        else:
            user._rooms = (user.rooms.filter(is_active=True) | user.manage_rooms.filter(is_active=True)).distinct()

    return user._rooms


def _user_get_full_name(user):
    """
    Override regular get_full_name which returns first_name + last_name
    """
    return user.profile.full_name


def _user_is_administrator(user):
    org_group = user.get_org_group()
    return org_group and org_group.name == 'Administrators'


def _user_has_room_access(user, room, manage=False):
    """
    Whether the given user has access to the given room
    """
    if user.is_superuser:
        return True
    elif user.is_administrator():
        return room.org == user.get_org()
    elif manage:
        return user.manage_rooms.filter(pk=room.pk).exists()
    else:
        return user.manage_rooms.filter(pk=room.pk).exists() or user.rooms.filter(pk=room.pk).exists()


User.get_full_name = _user_get_full_name
User.get_all_rooms = _user_get_all_rooms
User.is_administrator = _user_is_administrator
User.has_room_access = _user_has_room_access


######################### Monkey patching for the Org class #########################

ORG_CONFIG_SECRET_TOKEN = 'secret_token'
ORG_CONFIG_CHAT_NAME_FIELD = 'chat_name_field'


def _org_get_temba_client(org):
    return TembaClient(settings.SITE_API_HOST, org.api_token)


def _org_get_secret_token(org):
    return org.get_config(ORG_CONFIG_SECRET_TOKEN)


def _org_get_chat_name_field(org):
    return org.get_config(ORG_CONFIG_CHAT_NAME_FIELD)


Org.get_temba_client = _org_get_temba_client
Org.get_secret_token = _org_get_secret_token
Org.get_chat_name_field = _org_get_chat_name_field