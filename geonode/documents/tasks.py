#########################################################################
#
# Copyright (C) 2017 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################
import os

from celery.utils.log import get_task_logger

from geonode.celery_app import app
from geonode.storage.manager import storage_manager

from .models import Document
from .renderers import (
    render_document,
    generate_thumbnail_content,
    ConversionError)

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name='geonode.documents.tasks.create_document_thumbnail',
    queue='geonode',
    expires=600,
    time_limit=600,
    acks_late=False,
    autoretry_for=(Exception, ),
    retry_kwargs={'max_retries': 5},
    retry_backoff=3,
    retry_backoff_max=30,
    retry_jitter=False)
def create_document_thumbnail(self, object_id):
    """
    Create thumbnail for a document.
    """
    logger.debug(f"Generating thumbnail for document #{object_id}.")

    try:
        document = Document.objects.get(id=object_id)
    except Document.DoesNotExist:
        logger.error(f"Document #{object_id} does not exist.")
        raise

    image_path = None
    image_file = None

    if document.is_image:
        dname = storage_manager.path(document.files[0])
        if storage_manager.exists(dname):
            image_file = storage_manager.open(dname, 'rb')
    elif document.is_video or document.is_audio:
        image_file = open(document.find_placeholder(), 'rb')
    elif document.is_file:
        dname = storage_manager.path(document.files[0])
        try:
            document_location = storage_manager.path(dname)
        except NotImplementedError as e:
            logger.debug(e)

            document_location = storage_manager.url(dname)

        try:
            image_path = render_document(document_location)
            if image_path is not None:
                try:
                    image_file = open(image_path, 'rb')
                except Exception as e:
                    logger.debug(f"Failed to render document #{object_id}: {e}")
            else:
                logger.debug(f"Failed to render document #{object_id}")
        except ConversionError as e:
            logger.debug(f"Could not convert document #{object_id}: {e}.")
        except NotImplementedError as e:
            logger.debug(f"Failed to render document #{object_id}: {e}")

    thumbnail_content = None
    try:
        try:
            thumbnail_content = generate_thumbnail_content(image_file)
        except Exception as e:
            logger.debug(f"Could not generate thumbnail, falling back to 'placeholder': {e}")
            thumbnail_content = generate_thumbnail_content(document.find_placeholder())
    except Exception as e:
        logger.error(f"Could not generate thumbnail: {e}")
        return
    finally:
        if image_file is not None:
            image_file.close()

        if image_path is not None:
            os.remove(image_path)

    if not thumbnail_content:
        logger.warning(f"Thumbnail for document #{object_id} empty.")
    filename = f'document-{document.uuid}-thumb.png'
    document.save_thumbnail(filename, thumbnail_content)
    logger.debug(f"Thumbnail for document #{object_id} created.")


@app.task(
    bind=True,
    name='geonode.documents.tasks.delete_orphaned_document_files',
    queue='cleanup',
    expires=600,
    time_limit=600,
    acks_late=False,
    autoretry_for=(Exception, ),
    retry_kwargs={'max_retries': 5},
    retry_backoff=3,
    retry_backoff_max=30,
    retry_jitter=False)
def delete_orphaned_document_files(self):
    from geonode.documents.utils import delete_orphaned_document_files
    delete_orphaned_document_files()


@app.task(
    bind=True,
    name='geonode.documents.tasks.delete_orphaned_thumbnails',
    queue='cleanup',
    expires=600,
    time_limit=600,
    acks_late=False,
    autoretry_for=(Exception, ),
    retry_kwargs={'max_retries': 5},
    retry_backoff=3,
    retry_backoff_max=30,
    retry_jitter=False)
def delete_orphaned_thumbnails(self):
    from geonode.base.utils import delete_orphaned_thumbs
    delete_orphaned_thumbs()
