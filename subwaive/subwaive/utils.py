import secrets

from PIL import Image

from django.contrib.auth.decorators import login_required
from django.core import mail
from django.shortcuts import render, redirect
from subwaive.models import Log
from subwaive.settings import EMAIL_FROM

import qrcode
import qrcode.image.svg

CONFIDENTIALITY_LEVEL_CONFIDENTIAL = 'CONFIDENTIAL'
CONFIDENTIALITY_LEVEL_SENSITIVE = 'SENSITIVE'
CONFIDENTIALITY_LEVEL_PUBLIC = 'PUBLIC'

QR_SMALL = 10
QR_LARGE = 16

def generate_qr_svg(content, box_size=QR_SMALL):
    """ Return an SVG QR code encoding content """
    img = qrcode.make(content, image_factory=qrcode.image.svg.SvgImage, box_size=box_size)
    svg = img.to_string().decode("utf-8").replace('svg:rect','rect')

    return svg

def generate_qr_bitmap(content):
    """ Return a raw bitmap QR code encoding content """
    png = qrcode.make(content, version=5, box_size=4)

    return (png.tobytes(), png.size[0])


@login_required
def refresh(request, page_title, data_source, tiles, buttons=None):
    """ a page for initiating data refreshes """
    for tile in tiles:
        for d in tile['log_descriptions']:
            if 'last_refresh' in d.keys():
                d['last_refresh'] = Log.get_last("Refresh "+d['description']).timestamp
        for b in tile['buttons']:
            b['url'] = redirect(b['url_name']).url

    context = {
        'page_title': page_title,
        'data_source': data_source,
        'buttons': buttons,
        'tiles': tiles,
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_SENSITIVE,
    }

    return render(request, f'subwaive/data-refresh.html', context)

def url_secret():
    return secrets.token_urlsafe(16)

def send_email(email_to_address, email_body, email_html_body, email_subject):
    """ send an email """
    mail.send_mail(
        email_subject,
        email_body,
        EMAIL_FROM,
        [email_to_address],
        html_message=email_html_body
    )