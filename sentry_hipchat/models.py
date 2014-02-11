"""
sentry_hipchat.models
~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2011 by Linovia, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""

from django import forms
from django.conf import settings

from sentry.plugins.bases.notify import NotifyPlugin

import sentry_hipchat

import urllib
import urllib2
import json
import logging


COLORS = {
    'ALERT': 'orange',
    'ERROR': 'red',
    'WARNING': 'yellow',
    'INFO': 'green',
    'DEBUG': 'purple',
}


class HipchatOptionsForm(forms.Form):
    token = forms.CharField(help_text="Your hipchat API token.")
    room = forms.CharField(help_text="Room name or ID.")
    new_only = forms.BooleanField(help_text='Only send new messages.', required=False)
    notify = forms.BooleanField(help_text='Notify message in chat window.', required=False)
    include_project_name = forms.BooleanField(help_text='Include project name in message.', required=False)


class HipchatMessage(NotifyPlugin):
    author = 'Xavier Ordoquy'
    author_url = 'https://github.com/linovia/sentry-hipchat'
    version = sentry_hipchat.VERSION
    description = "Event notification to Hipchat."
    resource_links = [
        ('Bug Tracker', 'https://github.com/linovia/sentry-hipchat/issues'),
        ('Source', 'https://github.com/linovia/sentry-hipchat'),
    ]
    slug = 'hipchat'
    title = 'Hipchat'
    conf_title = title
    conf_key = 'hipchat'
    project_conf_form = HipchatOptionsForm
    timeout = getattr(settings, 'SENTRY_HIPCHAT_TIMEOUT', 3)

    def is_configured(self, project):
        return all((self.get_option(k, project) for k in ('room', 'token')))

    def on_alert(self, alert, **kwargs):
        project = alert.project
        token = self.get_option('token', project)
        room = self.get_option('room', project)
        notify = self.get_option('notify', project) or False
        include_project_name = self.get_option('include_project_name', project) or False

        if token and room:
            self.send_payload(token, room, '[ALERT]%(project_name)s %(message)s %(link)s' % {
                'project_name': (' <strong>%s</strong>' % project.name) if include_project_name else '',
                'message': '<pre>' + alert.message + '</pre>',
                'link': alert.get_absolute_url(),
            }, notify, color=COLORS['ALERT'])

    def post_process(self, group, event, is_new, is_sample, **kwargs):

        new_only = self.get_option('new_only', event.project)
        if new_only and not is_new:
            return

        token = self.get_option('token', event.project)
        room = self.get_option('room', event.project)
        notify = self.get_option('notify', event.project) or False
        include_project_name = self.get_option('include_project_name', event.project) or False
        level = event.get_level_display().upper()
        link = group.get_absolute_url()
        is_muted = group.is_muted()

        if token and room and not is_muted:
            self.send_payload(token, room, '[%(level)s]%(project_name)s %(message)s [<a href="%(link)s">view</a>]' % {
                'level': level,
                'project_name': (' <strong>%s</strong>' % event.project.name) if include_project_name else '',
                'message': '<pre>' + event.error() + '</pre>',
                'link': link,
            }, notify, color=COLORS.get(level, 'purple'))

    def send_payload(self, token, room, message, notify, color='red'):
        url = "https://api.hipchat.com/v1/rooms/message"
        values = {
            'auth_token': token,
            'room_id': room,
            'from': 'Sentry',
            'message': message,
            'notify': int(notify),
            'color': color,
        }
        data = urllib.urlencode(values)
        request = urllib2.Request(url, data)
        response = urllib2.urlopen(request, timeout=self.timeout)
        raw_response_data = response.read()
        response_data = json.loads(raw_response_data)
        if 'status' not in response_data:
            logger = logging.getLogger('sentry.plugins.hipchat')
            logger.error('Unexpected response')
        if response_data['status'] != 'sent':
            logger = logging.getLogger('sentry.plugins.hipchat')
            logger.error('Event was not sent to hipchat')
