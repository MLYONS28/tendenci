from south.signals import post_migrate
from south.models import MigrationHistory

from tendenci.apps.entities.models import Entity
from tendenci.core.site_settings.utils import get_setting


def create_default_entity(sender, app, **kwargs):
    """
    Auto-create a default entity if no entities exist.
    """
    if MigrationHistory.objects.filter(app_name="site_settings").count() > 0 and app == "entities" and not Entity.objects.exists():
        site_name = get_setting("site", "global", "sitedisplayname")
        entity = Entity()
        entity.allow_anonymous_view = False
        if site_name:
            entity.entity_name = site_name
        else:
            entity.entity_name = "Default"

        entity.save()

post_migrate.connect(create_default_entity)
