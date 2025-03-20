from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from subwaive.models import Log

import qrcode
import qrcode.image.svg

CONFIDENTIALITY_LEVEL_HIGH = 'HIGH'
CONFIDENTIALITY_LEVEL_PUBLIC = 'PUBLIC'

QR_SMALL = 10
QR_LARGE = 16

def generate_qr_svg(content, box_size=QR_SMALL):
    """ Return an SVG QR code encoding content """
    img = qrcode.make(content, image_factory=qrcode.image.svg.SvgImage, box_size=box_size)
    svg = img.to_string().decode("utf-8").replace('svg:rect','rect')

    return svg

@login_required
def refresh(request, log_descriptions, button_dict):
    """ a page for initiating data refreshes """
    datasets = [{'last_refresh': Log.get_last(d), 'description': d} for d in log_descriptions]
    for dataset in datasets:
        if dataset['last_refresh']:
            dataset['last_refresh'] = dataset['last_refresh'].timestamp

    buttons = [{'url': redirect(b['url_name']).url, 'anchor': b['anchor']} for b in button_dict]

    context = {
        'datasets': datasets,
        'buttons': buttons,
        'CONFIDENTIALITY_LEVEL': CONFIDENTIALITY_LEVEL_HIGH,
    }

    return render(request, f'subwaive/data-refresh.html', context)
