import copy
import json
import logging
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseNotFound
from django.utils.translation import ugettext as _
from le_utils.constants import content_kinds
from le_utils.constants import format_presets
from rest_framework.authentication import SessionAuthentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from contentcuration.models import Channel
from contentcuration.models import ContentNode
from contentcuration.models import ContentTag
from contentcuration.models import License
from contentcuration.models import PrerequisiteContentRelationship
from contentcuration.serializers import ContentNodeEditSerializer
from contentcuration.serializers import ContentNodeSerializer
from contentcuration.serializers import SimplifiedContentNodeSerializer
from contentcuration.serializers import TaskSerializer
from contentcuration.tasks import create_async_task
from contentcuration.tasks import getnodedetails_task
from contentcuration.utils.nodes import duplicate_node_bulk


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def get_node_diff(request, channel_id):
    original = []   # Currently imported nodes
    changed = []    # Nodes from original node
    fields_to_check = ['title', 'description', 'license', 'license_description', 'copyright_holder', 'author', 'extra_fields', 'language', 'role_visibility']
    assessment_fields_to_check = ['type', 'question', 'hints', 'answers', 'order', 'raw_data', 'source_url', 'randomize']

    current_tree_id = Channel.objects.get(pk=channel_id).main_tree.tree_id
    nodes = ContentNode.objects.prefetch_related('assessment_items').prefetch_related('files').prefetch_related('tags')

    copied_nodes = nodes.filter(tree_id=current_tree_id).exclude(original_source_node_id=F('node_id'))
    channel_ids = copied_nodes.values_list('original_channel_id', flat=True).exclude(original_channel_id=channel_id).distinct()
    tree_ids = Channel.objects.filter(pk__in=channel_ids).values_list("main_tree__tree_id", flat=True)
    original_node_ids = copied_nodes.values_list('original_source_node_id', flat=True).distinct()
    original_nodes = nodes.filter(tree_id__in=tree_ids, node_id__in=original_node_ids)

    # Use dictionary for faster lookup speed
    content_id_mapping = {n.content_id: n for n in original_nodes}

    for copied_node in copied_nodes:
        node = content_id_mapping.get(copied_node.content_id)

        if node:
            # Check lengths, metadata, tags, files, and assessment items
            node_changed = node.assessment_items.count() != copied_node.assessment_items.count() or \
                node.files.count() != copied_node.files.count() or \
                node.tags.count() != copied_node.tags.count() or \
                any(filter(lambda f: getattr(node, f, None) != getattr(copied_node, f, None), fields_to_check)) or \
                node.tags.exclude(tag_name__in=copied_node.tags.values_list('tag_name', flat=True)).exists() or \
                node.files.exclude(checksum__in=copied_node.files.values_list('checksum', flat=True)).exists() or \
                node.assessment_items.exclude(assessment_id__in=copied_node.assessment_items.values_list('assessment_id', flat=True)).exists()

            # Check individual assessment items
            if not node_changed and node.kind_id == content_kinds.EXERCISE:
                for ai in node.assessment_items.all():
                    source_ai = copied_node.assessment_items.filter(assessment_id=ai.assessment_id).first()
                    if source_ai:
                        node_changed = node_changed or any(filter(lambda f: getattr(ai, f, None) != getattr(source_ai, f, None), assessment_fields_to_check))
                        if node_changed:
                            break

            if node_changed:
                original.append(copied_node)
                changed.append(node)

    serialized_original = JSONRenderer().render(SimplifiedContentNodeSerializer(original, many=True).data)
    serialized_changed = JSONRenderer().render(SimplifiedContentNodeSerializer(changed, many=True).data)

    return HttpResponse(json.dumps({
        "original": serialized_original,
        "changed": serialized_changed,
    }))


def create_new_node(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)
    license = License.objects.filter(license_name=data.get('license_name')).first()  # Use filter/first in case preference hasn't been set
    license_id = license.pk if license else settings.DEFAULT_LICENSE
    new_node = ContentNode.objects.create(
        kind_id=data.get('kind'),
        title=data.get('title'),
        author=data.get('author'),
        aggregator=data.get('aggregator'),
        provider=data.get('provider'),
        copyright_holder=data.get('copyright_holder'),
        license_id=license_id,
        license_description=data.get('license_description'),
        parent_id=settings.ORPHANAGE_ROOT_ID,
    )
    return HttpResponse(JSONRenderer().render(ContentNodeEditSerializer(new_node).data))


@api_view(['GET'])
def get_prerequisites(request, get_postrequisites, ids):
    nodes = ContentNode.objects.prefetch_related('prerequisite').filter(pk__in=ids.split(","))

    request.user.can_view_nodes(nodes)

    prerequisite_mapping = {}
    postrequisite_mapping = {}
    prerequisite_tree_nodes = []

    for n in nodes:
        prereqs, prereqmapping = n.get_prerequisites()
        if get_postrequisites == "true":
            postreqs, postreqmapping = n.get_postrequisites()
            postrequisite_mapping.update(postreqmapping)
            prerequisite_mapping.update(prereqmapping)
            prerequisite_tree_nodes += prereqs + postreqs + [n]
        else:
            prerequisite_mapping.update({n.pk: prereqmapping})
            prerequisite_tree_nodes += prereqs + [n]

    return Response({
        "prerequisite_mapping": prerequisite_mapping,
        "postrequisite_mapping": postrequisite_mapping,
        "prerequisite_tree_nodes": SimplifiedContentNodeSerializer(prerequisite_tree_nodes, many=True).data,
    })


@api_view(['GET'])
def get_total_size(request, ids):
    sizes = ContentNode.objects.prefetch_related('assessment_items', 'files', 'children')\
                       .exclude(kind_id=content_kinds.EXERCISE, published=False)\
                       .filter(id__in=ids.split(",")).get_descendants(include_self=True)\
                       .values('files__checksum', 'files__file_size')\
                       .distinct().aggregate(resource_size=Sum('files__file_size'))

    return HttpResponse(json.dumps({'success': True, 'size': sizes['resource_size'] or 0}))


@api_view(['GET'])
def get_nodes_by_ids(request, ids):
    nodes = ContentNode.objects.prefetch_related('children', 'files', 'assessment_items', 'tags')\
                       .filter(pk__in=ids.split(","))\
                       .defer('node_id', 'original_source_node_id', 'source_node_id', 'content_id',
                              'original_channel_id', 'source_channel_id', 'source_id', 'source_domain', 'created', 'modified')
    serializer = ContentNodeSerializer(nodes, many=True)
    return Response(serializer.data)


def get_node_path(request, topic_id, tree_id, node_id):
    try:
        topic = ContentNode.objects.prefetch_related('children').get(node_id__startswith=topic_id, tree_id=tree_id)

        if topic.kind_id != content_kinds.TOPIC:
            node = ContentNode.objects.prefetch_related('files', 'assessment_items', 'tags').get(node_id__startswith=topic_id, tree_id=tree_id)
            nodes = node.get_ancestors(ascending=True)
        else:
            node = node_id and ContentNode.objects.prefetch_related('files', 'assessment_items', 'tags').get(node_id__startswith=node_id, tree_id=tree_id)
            nodes = topic.get_ancestors(include_self=True, ascending=True)

        return HttpResponse(json.dumps({
            'path': JSONRenderer().render(ContentNodeSerializer(nodes, many=True).data),
            'node': node and JSONRenderer().render(ContentNodeEditSerializer(node).data),
            'parent_node_id': topic.kind_id != content_kinds.TOPIC and node.parent and node.parent.node_id
        }))
    except ObjectDoesNotExist:
        return HttpResponseNotFound("Invalid URL: the referenced content does not exist in this channel.")


@api_view(['GET'])
def get_nodes_by_ids_simplified(request, ids):
    nodes = ContentNode.objects.prefetch_related('children').filter(pk__in=ids.split(","))
    serializer = SimplifiedContentNodeSerializer(nodes, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def get_nodes_by_ids_complete(request):
    ids = json.loads(request.GET['nodes'])
    nodes = ContentNode.objects.prefetch_related('children', 'files', 'assessment_items', 'tags').filter(pk__in=ids)
    serializer = ContentNodeEditSerializer(nodes, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def get_topic_details(request, contentnode_id):
    """ Generates data for topic contents. Used for look-inside previews
        Keyword arguments:
            contentnode_id (str): id of topic node to get details from
    """
    # Get nodes and channel
    node = ContentNode.objects.get(pk=contentnode_id)
    data = get_node_details_cached(node)
    return HttpResponse(json.dumps(data))


def get_node_details_cached(node):
    cached_data = cache.get("details_{}".format(node.node_id))

    if cached_data:
        descendants = node.get_descendants().prefetch_related('children', 'files', 'tags') \
            .select_related('license', 'language')
        channel = node.get_channel()

        # If channel is a sushi chef channel, use date created for faster query
        # Otherwise, find the last time anything was updated in the channel
        last_update = channel.main_tree.created if channel and channel.ricecooker_version else \
            descendants.filter(changed=True) \
            .aggregate(latest_update=Max('modified')) \
            .get('latest_update')

        if last_update:
            last_cache_update = datetime.strptime(json.loads(cached_data)['last_update'], settings.DATE_TIME_FORMAT)
            if last_update.replace(tzinfo=None) > last_cache_update:
                # update the stats async, then return the cached value
                getnodedetails_task.apply_async((node.pk,))
        return json.loads(cached_data)

    return node.get_details()


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def delete_nodes(request):
    logging.debug("Entering the copy_node endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)

    try:
        nodes = data["nodes"]
        channel_id = data["channel_id"]
        request.user.can_edit(channel_id)
        nodes = ContentNode.objects.filter(pk__in=nodes)
        for node in nodes:
            if node.parent and not node.parent.changed:
                node.parent.changed = True
                node.parent.save()
            node.delete()

    except KeyError:
        raise ObjectDoesNotExist("Missing attribute from data: {}".format(data))

    return HttpResponse(json.dumps({'success': True}))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def duplicate_nodes(request):
    logging.debug("Entering the copy_node endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)

    try:
        node_ids = data["node_ids"]
        sort_order = data.get("sort_order") or 1
        channel_id = data["channel_id"]
        target_parent = ContentNode.objects.get(pk=data["target_parent"])
        channel = target_parent.get_channel()
        request.user.can_edit(channel and channel.pk)

        task_info = {
            'user': request.user,
            'metadata': {
                'affects': {
                    'channels': [channel_id],
                    'nodes': node_ids,
                }
            }
        }

        task_args = {
            'user_id': request.user.pk,
            'channel_id': channel_id,
            'target_parent': target_parent.pk,
            'node_ids': node_ids,
            'sort_order': sort_order
        }

        task, task_info = create_async_task('duplicate-nodes', task_info, task_args)
        return HttpResponse(JSONRenderer().render(TaskSerializer(task_info).data))
    except KeyError:
        raise ObjectDoesNotExist("Missing attribute from data: {}".format(data))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def duplicate_node_inline(request):
    logging.debug("Entering the copy_node endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)

    try:

        node = ContentNode.objects.get(pk=data["node_id"])
        channel_id = data["channel_id"]
        target_parent = ContentNode.objects.get(pk=data["target_parent"])
        channel = target_parent.get_channel()
        request.user.can_edit(channel and channel.pk)

        # record_node_duplication_stats([node], ContentNode.objects.get(pk=target_parent.pk),
        #                               Channel.objects.get(pk=channel_id))

        new_node = None
        with transaction.atomic():
            with ContentNode.objects.disable_mptt_updates():
                sort_order = (node.sort_order + node.get_next_sibling().sort_order) / 2 if node.get_next_sibling() else node.sort_order + 1
                new_node = duplicate_node_bulk(node, sort_order=sort_order, parent=target_parent, channel_id=channel_id, user=request.user)
                if not new_node.title.endswith(_(" (Copy)")):
                    new_node.title = new_node.title + _(" (Copy)")
                    new_node.save()

        return HttpResponse(JSONRenderer().render(ContentNodeSerializer(ContentNode.objects.filter(pk=new_node.pk), many=True).data))

    except KeyError:
        raise ObjectDoesNotExist("Missing attribute from data: {}".format(data))


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def move_nodes(request):
    logging.debug("Entering the move_nodes endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)

    try:
        nodes = data["nodes"]
        target_parent = ContentNode.objects.get(pk=data["target_parent"])
        channel_id = data["channel_id"]
        min_order = data.get("min_order") or 0
        max_order = data.get("max_order") or min_order + len(nodes)

        channel = target_parent.get_channel()
        request.user.can_edit(channel and channel.pk)

    except KeyError:
        return ObjectDoesNotExist("Missing attribute from data: {}".format(data))

    all_ids = []

    with ContentNode.objects.delay_mptt_updates():
        for n in nodes:
            min_order = min_order + float(max_order - min_order) / 2
            node = ContentNode.objects.get(pk=n['id'])
            _move_node(node, parent=target_parent, sort_order=min_order, channel_id=channel_id)
            all_ids.append(n['id'])

    serialized = ContentNodeSerializer(ContentNode.objects.filter(pk__in=all_ids), many=True).data
    return HttpResponse(JSONRenderer().render(serialized))


def _move_node(node, parent=None, sort_order=None, channel_id=None):
    # if we move nodes, make sure the parent is marked as changed
    if node.parent and not node.parent.changed:
        node.parent.changed = True
        node.parent.save()
    node.parent = parent or node.parent
    node.sort_order = sort_order or node.sort_order
    node.changed = True
    descendants = node.get_descendants(include_self=True)

    if node.tree_id != parent.tree_id:
        PrerequisiteContentRelationship.objects.filter(Q(target_node_id=node.pk) | Q(prerequisite_id=node.pk)).delete()

    node.save()
    # we need to make sure the new parent is marked as changed as well
    if node.parent and not node.parent.changed:
        node.parent.changed = True
        node.parent.save()

    for tag in ContentTag.objects.filter(tagged_content__in=descendants).distinct():
        # If moving from another channel
        if tag.channel_id != channel_id:
            t, is_new = ContentTag.objects.get_or_create(tag_name=tag.tag_name, channel_id=channel_id)

            # Set descendants with this tag to correct tag
            for n in descendants.filter(tags=tag):
                n.tags.remove(tag)
                n.tags.add(t)

    return node


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def sync_nodes(request):
    logging.debug("Entering the sync_nodes endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)

    try:
        nodes = data["nodes"]
        channel_id = data['channel_id']

    except KeyError:
        return ObjectDoesNotExist("Missing attribute from data: {}".format(data))

    all_nodes = []
    with transaction.atomic(), ContentNode.objects.delay_mptt_updates():
        for n in nodes:
            node, _ = _sync_node(ContentNode.objects.get(pk=n), channel_id, sync_attributes=True, sync_tags=True, sync_files=True, sync_assessment_items=True)
            if node.changed:
                node.save()
            all_nodes.append(node)
    return HttpResponse(JSONRenderer().render(ContentNodeSerializer(all_nodes, many=True).data))


def _sync_node(node, channel_id, sync_attributes=False, sync_tags=False, sync_files=False, sync_assessment_items=False, sync_sort_order=False):
    parents_to_check = []
    original_node = node.get_original_node()
    if original_node.node_id != node.node_id:  # Only update if node is not original
        logging.info("----- Syncing: {} from {}".format(node.title.encode('utf-8'), original_node.get_channel().name.encode('utf-8')))
        if sync_attributes:  # Sync node metadata
            sync_node_data(node, original_node)
        if sync_tags:  # Sync node tags
            sync_node_tags(node, original_node, channel_id)
        if sync_files:  # Sync node files
            sync_node_files(node, original_node)
        if sync_assessment_items and node.kind_id == content_kinds.EXERCISE:  # Sync node exercises
            sync_node_assessment_items(node, original_node)
        if sync_sort_order:  # Sync node sort order
            node.sort_order = original_node.sort_order
            if node.parent not in parents_to_check:
                parents_to_check.append(node.parent)
    return node, parents_to_check


@authentication_classes((TokenAuthentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def sync_channel_endpoint(request):
    logging.debug("Entering the sync_nodes endpoint")

    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests are allowed on this endpoint.")

    data = json.loads(request.body)

    try:
        nodes = sync_channel(
            Channel.objects.get(pk=data['channel_id']),
            sync_attributes=data.get('attributes'),
            sync_tags=data.get('tags'),
            sync_files=data.get('files'),
            sync_assessment_items=data.get('assessment_items'),
            sync_sort_order=data.get('sort'),
        )

        return HttpResponse(JSONRenderer().render(ContentNodeSerializer(nodes, many=True).data))
    except KeyError:
        return ObjectDoesNotExist("Missing attribute from data: {}".format(data))


def sync_channel(channel, sync_attributes=False, sync_tags=False, sync_files=False, sync_assessment_items=False, sync_sort_order=False):
    all_nodes = []
    parents_to_check = []  # Keep track of parents to make resorting easier

    with transaction.atomic():
        with ContentNode.objects.delay_mptt_updates():
            logging.info("Syncing nodes for channel {} (id:{})".format(channel.name, channel.pk))
            for node in channel.main_tree.get_descendants():
                node, parents = _sync_node(node, channel.pk,
                                           sync_attributes=sync_attributes,
                                           sync_tags=sync_tags,
                                           sync_files=sync_files,
                                           sync_assessment_items=sync_assessment_items,
                                           sync_sort_order=sync_sort_order,
                                           )
                parents_to_check += parents
                all_nodes.append(node)
            # Avoid cases where sort order might have overlapped
            for parent in parents_to_check:
                sort_order = 1
                for child in parent.children.all().order_by('sort_order', 'title'):
                    child.sort_order = sort_order
                    child.save()
                    sort_order += 1

    return all_nodes


def sync_node_data(node, original):
    node.title = original.title
    node.description = original.description
    node.license = original.license
    node.copyright_holder = original.copyright_holder
    node.changed = True
    node.author = original.author
    node.extra_fields = original.extra_fields


def sync_node_tags(node, original, channel_id):
    # Remove tags that aren't in original
    for tag in node.tags.exclude(tag_name__in=original.tags.values_list('tag_name', flat=True)):
        node.tags.remove(tag)
        node.changed = True
    # Add tags that are in original
    for tag in original.tags.exclude(tag_name__in=node.tags.values_list('tag_name', flat=True)):
        new_tag, is_new = ContentTag.objects.get_or_create(
            tag_name=tag.tag_name,
            channel_id=channel_id,
        )
        node.tags.add(new_tag)
        node.changed = True


def sync_node_files(node, original):
    """
    Sync all files in ``node`` from the files in ``original`` node.
    """
    # A. Delete files that aren't in original
    node.files.exclude(checksum__in=original.files.values_list('checksum', flat=True)).delete()
    # B. Add all files that are in original
    for f in original.files.all():
        # 1. Look for old file with matching preset (and language if subs file)
        if f.preset_id == format_presets.VIDEO_SUBTITLE:
            oldf = node.files.filter(preset=f.preset, language=f.language).first()
        else:
            oldf = node.files.filter(preset=f.preset).first()
        # 2. Remove oldf if it exists and its checksum has changed
        if oldf:
            if oldf.checksum == f.checksum:
                continue             # No need to copy file if it hasn't changed
            else:
                oldf.delete()
                node.changed = True
        # 3. Copy over new file from original node
        fcopy = copy.copy(f)
        fcopy.id = None
        fcopy.contentnode = node
        fcopy.save()
        node.changed = True


def sync_node_assessment_items(node, original):
    node.extra_fields = original.extra_fields
    node.changed = True
    # Clear assessment items on node
    node.assessment_items.all().delete()
    # Add assessment items onto node
    for ai in original.assessment_items.all():
        ai_copy = copy.copy(ai)
        ai_copy.id = None
        ai_copy.contentnode = node
        ai_copy.save()
        for f in ai.files.all():
            f_copy = copy.copy(f)
            f_copy.id = None
            f_copy.assessment_item = ai_copy
            f_copy.save()
