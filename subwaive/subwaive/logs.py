import datetime
import logging
import os
import pytz

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from subwaive.models import Log

DATA_REFRESH_TOKEN = os.environ.get("DATA_REFRESH_TOKEN")

TIME_ZONE = os.environ.get("TIME_ZONE")

@csrf_exempt
def thin_logs_by_token(request):
    """ allow stratified log deletion by token """

    if request.headers.get('X-Refresh-Token') == DATA_REFRESH_TOKEN:
        print(datetime.datetime.now(), "Thinning old logs by token")
        retention_schedule = [
            {'level': logging.NOTSET, 'horizon': datetime.timedelta(weeks=24)},
            {'level': logging.DEBUG, 'horizon': datetime.timedelta(days=7)},
            {'level': logging.INFO, 'horizon': datetime.timedelta(weeks=4)},
            {'level': logging.WARN, 'horizon': datetime.timedelta(weeks=12)},
            {'level': logging.ERROR, 'horizon': datetime.timedelta(weeks=24)},
            {'level': logging.CRITICAL, 'horizon': datetime.timedelta(weeks=24)},
        ]

        for r in retention_schedule:
            Log.objects.filter(logging_level=r['level'],timestamp__lte=datetime.datetime.now().astimezone(pytz.timezone(TIME_ZONE))-r['horizon']).delete()

        Log.new(logging_level=logging.INFO, description='Thin logs by token')

        return HttpResponse(status=200)
    else:
        return HttpResponse(status=401)


# Fix logging level fields by partition
# Log.objects.filter(logging_level=0,description__contains="Create").update(logging_level=10)
# Log.objects.filter(logging_level=0,description__contains="Clear unused").update(logging_level=10)
# Log.objects.filter(logging_level=0,description__contains="Update").update(logging_level=10)
# Log.objects.filter(logging_level=0,description__contains="Fetch").update(logging_level=20)
# Log.objects.filter(logging_level=0,description__contains="Merge").update(logging_level=20)
# Log.objects.filter(logging_level=0,description__contains="Auto-name").update(logging_level=20)
# Log.objects.filter(logging_level=0,description__contains="Refresh").update(logging_level=20)
# Log.objects.filter(logging_level=0,description__contains=" webhook").update(logging_level=20)
