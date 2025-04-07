from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from subwaive.models import QRCustom
from subwaive.utils import generate_qr_svg, CONFIDENTIALITY_LEVEL_PUBLIC, CONFIDENTIALITY_LEVEL_SENSITIVE, QR_SMALL, QR_LARGE


@login_required
def public_link_list(request):
    return custom_link_list(request, is_sensitive=False)

@login_required
def sensitive_link_list(request):
    return custom_link_list(request, is_sensitive=True)

@login_required
def custom_link_list(request, is_sensitive=False):
    """ Build a list of links to QR codes """
    user_qr_codes = QRCustom.objects.filter(category__is_sensitive=is_sensitive).order_by('category','name')

    user_qr_list = [
        {
            'id' : qr.id,
            'category': qr.category.name,
            'name': qr.name,
            'svg_small': generate_qr_svg(qr.content, QR_SMALL),
            'svg_large': generate_qr_svg(qr.content,QR_LARGE ),
            'url': qr.content if 'https' in qr.content else None
        }
        for qr in user_qr_codes
    ]

    categories = [
        {
            'name': category[0],
            'baseid': f'cat-{ category[1] }',
        }
        for category in set([(c.category.name, c.category.id) for c in user_qr_codes])
    ]
    categories = sorted(categories, key=lambda x: x['name'])

    if is_sensitive:
        confidentiality_level = CONFIDENTIALITY_LEVEL_SENSITIVE
    else:
        confidentiality_level = CONFIDENTIALITY_LEVEL_PUBLIC

    context = {
        'page_title': 'Links',
        'CONFIDENTIALITY_LEVEL': confidentiality_level,
        'categories': categories,
        'qr_list': user_qr_list,
    }

    return render(request, f'subwaive/qr-links.html', context)
