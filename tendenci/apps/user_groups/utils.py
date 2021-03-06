from collections import OrderedDict
import time
from datetime import datetime, date
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.utils.encoding import smart_str

from tendenci.apps.user_groups.models import Group
from tendenci.apps.subscribers.models import GroupSubscription, SubscriberData
from tendenci.core.base.utils import UnicodeWriter

def member_choices(group, member_label):
    """
    Creates a list of 2 tuples of a user's pk and the selected
    member label. This is used for generating choices for a form.
    choices for member label are: email, full name and username.
    """
    members = User.objects.filter(is_active=1)
    if member_label == 'email':
        label = lambda x: x.email
    elif member_label == 'full_name':
        label = lambda x: x.get_full_name()
    else:
        label = lambda x: x.username
    choices = []
    for member in members:
        choices.append((member.pk, label(member)))
    return choices


def get_default_group():
    """
    get lowest id group to use as default in other apps that FK to Group
    """
    return (Group.objects.filter(
        status=True, status_detail="active").order_by('id')[:1] or [None])[0]


def process_export(
        group_id,
        export_target='all',
        identifier=u'', user_id=0):
    """
    Process export for group members and/or group subscribers.
    """

    [group] = Group.objects.filter(id=group_id)[:1] or [None]
    if not group:
        return

    # pull 100 rows per query
    # be careful of the memory usage
    rows_per_batch = 100

    identifier = identifier or int(time.time())
    file_dir = 'export/groups/'
    
    file_name_temp = '%sgroup_%d_%s_%d_temp.csv' % (file_dir,
                                                 group.id,
                                                 export_target,
                                                identifier)
    
    # labels
    subscribers_labels = None
    regular_labels = None
    if export_target in ['subscribers', 'all']: 
        
        # get a list of labels for subscribers
        subscribers_labels = list(set([label for (label, ) in
                                  SubscriberData.objects.filter(
                                          subscription__group=group
                                          ).values_list('field_label')
                                  ]))
                                 
    if export_target in ['regular', 'all']:
        user_fields = [
                        'id',
                        'first_name',
                        'last_name',
                        'email',
                        'is_active',
                        'is_staff',
                        'is_superuser'
                       ]
        profile_fields = [
                          'direct_mail',
                          'company',
                          'address', 
                          'address2',
                          'city',
                          'state',
                          'zipcode',
                          'country',
                          'phone',
                          'create_dt'
                          ]
        regular_labels = user_fields + profile_fields

    if regular_labels and subscribers_labels:
        labels = regular_labels + subscribers_labels
    elif regular_labels:
        labels = regular_labels
    elif subscribers_labels:
        labels = subscribers_labels
        
    
    field_dict = OrderedDict([(label.lower().replace(" ", "_"), ''
                               ) for label in labels])

    with default_storage.open(file_name_temp, 'wb') as csvfile:
        csv_writer = UnicodeWriter(csvfile, encoding='utf-8')
        csv_writer.writerow(field_dict.keys())
        
        # process regular group members
        if export_target in ['regular', 'all']:
            count_members = group.members.filter(
                            group_member__status=True,
                            group_member__status_detail='active'
                            ).count()
            num_rows_processed = 0
            while num_rows_processed < count_members:
                users = group.members.filter(
                            group_member__status=True,
                            group_member__status_detail='active'
                            ).select_related('profile'
                            )[num_rows_processed:(num_rows_processed + rows_per_batch)]
                num_rows_processed += rows_per_batch
                row_dict = field_dict.copy()
                for user in users:
                    profile = user.profile
                    for field_name in user_fields:
                        if hasattr(user, field_name):
                            row_dict[field_name] = getattr(user, field_name)
                    for field_name in profile_fields:
                        if hasattr(profile, field_name):
                            row_dict[field_name] = getattr(profile, field_name)
                    for k, v in row_dict.items():
                        if not isinstance(v, basestring):
                            if isinstance(v, datetime):
                                row_dict[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                            elif isinstance(v, date):
                                row_dict[k] = v.strftime('%Y-%m-%d')
                            else:
                                row_dict[k] = smart_str(v)
                                
                    csv_writer.writerow(row_dict.values())

        # process for subscribers
        if export_target in ['subscribers', 'all']:
            count_subscriptions = GroupSubscription.objects.filter(
                                        group=group
                                        ).count()

            num_rows_processed = 0
            while num_rows_processed < count_subscriptions:
                subscription_ids = GroupSubscription.objects.filter(
                                    group=group
                                    ).order_by('id'
                                    ).values_list('id', flat=True
                                    )[num_rows_processed:(num_rows_processed + rows_per_batch)]
                num_rows_processed += rows_per_batch
                if subscription_ids:
                    ssdata = SubscriberData.objects.filter(
                                            subscription__group=group,
                                            subscription_id__in=subscription_ids
                                            )
                    if ssdata:
                        row_dict = field_dict.copy()
                        for sd in ssdata:
                            field_name = sd.field_label.lower().replace(" ", "_")
                            row_dict[field_name] = sd.value
                        csv_writer.writerow(row_dict.values())

            

    # rename the file name
    file_name = '%sgroup_%d_%s_%d.csv' % (file_dir,
                                         group.id,
                                         export_target,
                                        identifier)
    default_storage.save(file_name, default_storage.open(file_name_temp, 'rb'))

    # delete the temp file
    default_storage.delete(file_name_temp)
    print file_name
