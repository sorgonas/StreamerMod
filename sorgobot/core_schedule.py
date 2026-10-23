"""Five-field cron schedules in the configured Linux timezone."""
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo
from croniter import croniter

class CronSchedules:
    def __init__(self,studio):self.studio=studio;self.due={};self.failed={}
    def now(self,item):return dt.datetime.now(ZoneInfo(item.get('timezone') or self.studio.config.get('timezone','Europe/Berlin')))
    async def run(self):
        while True:
            wanted={i['id']:i for i in self.studio.core_services.config['cronSchedules'] if i.get('enabled',True)}
            for identity in self.due.keys()-wanted.keys():self.due.pop(identity)
            for identity,item in wanted.items():
                try:
                    now=self.now(item)
                    signature=(item['expression'],str(now.tzinfo))
                    if identity not in self.due or self.due[identity][0]!=signature:self.due[identity]=(signature,croniter(item['expression'],now).get_next(dt.datetime))
                    _,due=self.due[identity]
                    if now>=due:
                        self.due[identity]=(signature,croniter(item['expression'],now).get_next(dt.datetime))
                        self.studio.engine.core_events.emit(90270,{'scheduleId':identity,'scheduleName':item['name'],'scheduledAt':due.isoformat()},scheduleId=identity)
                    self.failed.pop(identity,None)
                except (ValueError,KeyError) as error:
                    if self.failed.get(identity)!=str(error):self.studio.io.trace('cron_error',name=item['name'],error=str(error));self.failed[identity]=str(error)
            await asyncio.sleep(.5)
