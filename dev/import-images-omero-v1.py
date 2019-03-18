#!/usr/bin/env python2

#
# Code from: https://gist.github.com/will-moore/f5402e451ea471fd05893f8b38a077ce
# from http://www.openmicroscopy.org/community/viewtopic.php?f=6&t=8407
# Uses code from https://github.com/openmicroscopy/openmicroscopy/blob/develop/components/tools/OmeroPy/src/omero/testlib/__init__.py

# https://docs.openmicroscopy.org/omero/5.4.10/users/cli/containers-annotations.html
# https://docs.openmicroscopy.org/omero/5.4.10/developers/Python.html

# API
# https://downloads.openmicroscopy.org/omero/5.4.10/api/python/
#
# https://docs.openmicroscopy.org/omero/5.4.10/developers/Model/EveryObject.html#omero-model-class-wellsample
#
#
# docker-compose up
# docker exec -it omero-server-dev /scripts/import-images-omero-v1.py
#
# Python path
# export PYTHONPATH=$PYTHONPATH:/home/anders/projekt/pharmbio/OMERO/dev/OMERO.server-5.4.10-ice36-b105/lib/python
# export PYTHONPATH=$PYTHONPATH:/opt/omero/server/OMERO.server/lib/python/
# export OMERO_DEV_PASSW=devpass
# /scripts/import-images-omero-v1.py

import platform
import os
from os.path import relpath
import re
import datetime
import time
import fnmatch
import logging
import sys
import cStringIO
import json

import omero
from omero.gateway import BlitzGateway
from omero.cli import cli_login
from omero.rtypes import rstring, rint, rdouble, rtime

# read password from environment
omero_rootpass = os.environ['ROOTPASS']

#
# Adopted from: https://github.com/HASTE-project/haste-image-analysis-container2/tree/master/haste/image_analysis_container2/filenames
# path example
# 'ACHN-20X-P009060/2019-02-19/and-more/not/needed/'
__pattern_path_plate_date = re.compile('^'
                            + '([^-]+)'  # screen-name (1)
                            + '-([^-]+)'  # magnification (2)
                            + '-([^/]+)'  # plate (3)
                            + '/([^/]+)'  # date (4)
                            ,
                            re.IGNORECASE)  # Windows has case-insensitive filenames

# Adopted from: https://github.com/HASTE-project/haste-image-analysis-container2/tree/master/haste/image_analysis_container2/filenames
# file example
# /share/mikro/IMX/MDC Polina Georgiev/exp-WIDE/ACHN-20X-P009060/2019-02-19/51/ACHN-20X-P009060_G11_s9_w52B1ACE5F-5E6A-4AEC-B227-016795CE2297.tif
__pattern_path_and_file   = re.compile('^'
                            + '.*'        # any
                            + '([0-9]{4})-([0-9]{2})-([0-9]{2})' # date (yyyy, mm, dd) (1,2,3)
                            + '.*\/'      # any until last /
                            + '([^-]+)'   # screen-name (4)
                            + '-([^-]+)'  # magnification (5)
                            + '-([^_]+)'  # plate (6)
                            + '_([^_]+)'  # well (7)
                            + '_s([^_]+)'  # wellsample (8)
                            + '_w([0-9]+)' # Channel (color channel?) (9)
                            + '(_thumb)?'  # Thumbnail (10)
                            #+ '.*\.'      # any until last . Image GUID
                            #+ '(\.tiff?)?'  # Extension (11)
                            #+ '$'
                            ,
                            re.IGNORECASE)  # Windows has case-insensitive filenames


def parse_path_plate_date(path):
  match = re.search(__pattern_path_plate_date, path)

  if match is None:
    return None

  metadata = {
    'screen': match.group(1),
    'magnification': match.group(2),
    'plate': match.group(3),
    'date': match.group(4),

  }

  return metadata

def parse_path_and_file(path):
  match = re.search(__pattern_path_and_file, path)

  if match is None:
    return None

  metadata = {
    'path': path,
    'filename': os.path.basename(path),
    'date_year': int(match.group(1)),
    'date_month': int(match.group(2)),
    'date_day_of_month': int(match.group(3)),
    'screen': match.group(4),
    'magnification': match.group(5),
    'plate': match.group(6),
    'well': match.group(7),
    'wellsample': match.group(8),
    'color_channel': int(match.group(9)),
    'is_thumbnail': match.group(10) is not None,
    #'guid': match.group(11),
    #'extension': match.group(12),
  }

  return metadata

#
# Executes a command with the omero-cli program /...server.../bin/omero
# Method redirects stdout so return values on stdout can be read in Python
#
def execOmeroCommand(args):
  logging.info("exec command:" + str(args))
  stdout_ = sys.stdout
  redirected_stdout = cStringIO.StringIO()
  sys.stdout = redirected_stdout
  retval = ""

  with cli_login("--server","localhost","--port", "4064", "--user","root", "--password", omero_rootpass ) as cli:
    logging.info("Before command")
    cli.invoke(args)
    logging.info("After command")
    retval = redirected_stdout.getvalue()
    cli.close()

  # restore stream
  sys.stdout = stdout_
  logging.info("retval " + retval)
  return retval

#
# Indirect relies on omero-cli program /...server.../bin/omero
# executes a subcommand with that binary
#
def uploadImage(filepath):
  filename = os.path.basename(filepath)

  args = ["import",
          "--quiet",
          "--transfer", "ln_s",
          "--skip","all",
          filepath
          ]

  result = execOmeroCommand(args)

#
# From a list of files/directories instead of a single file/directory
#
def uploadImages(file_list):

  for filepath in file_list:
    filename = os.path.basename(filepath)
    result = uploadImage(filepath)
    logging.debug(result)

#
# Create a connection to server (This is for commands that are executed
# direct with python API and not via the /bin/omero command line client)
#
def getOmeroConn():
  conn = BlitzGateway("root", omero_rootpass, host="localhost", port="4064")
  conn.connect()
  return conn


def searchObjects(conn, obj_types, text, fieldsxx):
  return conn.searchObjects(obj_types, text, fields=["name"])

#
# Older version of search (it is not working as expected, returning
# more than one result even if perfect match only should return one
#
# Throws Exception if more than one object is returned
#
def getID_v1(conn, obj_types, text, fields):
  logging.info("text:" + text)
  logging.info("fields:" + str(fields))
  result = searchObjects(conn, obj_types, text, fields)
  logging.debug("result:" + str(result))
  if result is None or len(result) == 0:
    return None
  if len(result) > 1:
    raise Exception('Get ID returned more than 1 results')
  return result.getId()
  
#
# Older version of search (it is not working as expected, returning
# more than one result even if perfect match only should return one
#
def getPlateID_v1(conn, name):
  return getID(conn, ["Plate"], name, fields=("name",))
  

#
# Searches with OMERO findAllByQuery method
#
# Throws Exception if more than one object is returned
#
def getID(conn, table, search, field):
  qs = conn.getQueryService()
  params = omero.sys.Parameters()
  params.map = {'text': rstring(search)}
  result = qs.findAllByQuery("from " + table + " as i where i." + field + "=:text", params)
  if result is None or len(result) == 0:
    return None
  if len(result) > 1:
    raise Exception('Get ID returned more than 1 results')
  return result[0].getId()

#
# Throws Exception if more than one result is found
#
def getImageID(conn, name):
  return getID(conn, "Image", name, "name")

#
# Throws Exception if more than one result is found
#
def getPlateID(conn, name):
  return getID(conn, "Plate", name, "name")

#
# Returns list of files
#
def recursive_glob(rootdir='.', pattern='*'):
  matches = []
  for root, dirnames, filenames in os.walk(rootdir):
    for filename in fnmatch.filter(filenames, pattern):
      matches.append(os.path.join(root, filename))
  return matches

#
# Recurses dir and returns time of file with last modification date
#
def getLastModificationInDir(path, pattern):
  files = recursive_glob(path, pattern)
  logging.debug(files)
  latest_file = max(files, key=os.path.getctime)
  logging.debug("latest_file: " + str(latest_file))
  modTimeInEpoc = os.path.getmtime(latest_file)
  modificationTime = datetime.datetime.utcfromtimestamp(modTimeInEpoc)
  return modificationTime

#
# Returns list of (level 1) subdirs to specified dir
#
def get_subdirs(root_path):
  subdirs = []
  for name in os.listdir(root_path):
    if os.path.isdir(os.path.join(root_path, name)):
      subdirs.append(os.path.join(root_path, name))
  return subdirs

#
# Recursively gets all (valid) imagefiles from thi "root-dir"
# e.g. *.tif, jpg and not *thumb"
#
def get_all_valid_images(path):
  all_files = recursive_glob(path, '*')

  logging.debug("all_files:" + str(all_files))

  pattern_file_filter = re.compile('^(?!.*thumb)(?=.*tif|.*jpg)') # not "thumb" but contains tif or jpg
  filtered_files = filter(pattern_file_filter.match, all_files)

  logging.debug("filtered_files:" + str(filtered_files))

  return filtered_files


#
# Return row and col index as integer from well label, e.g. 'A07'
#
def well_label2row_col(label):
  row = ord(label[0].lower()) - 96 # 97 is character a in ascii
  col = int(label[1] + label[2])
  row_col = {
    'row': row,
    'col': col
  }
  return row_col

def dictToMapAnnotation(d):
  map_ann = []
  for key, value in d.iteritems():
    # values has to be string for omero
    key_val = [key, str(value)]
    map_ann.append(key_val)

  return map_ann

#
# Currently sorting on full filename will do fine
#
def image_name_sort_fn(filename):
  return filename

def import_plate_images_and_meta(plate_subdir, conn):
  logging.debug("start import_plate_images_and_meta:" + str(plate_subdir))
  all_images = get_all_valid_images(plate_subdir)

  # Check that no image is in database already
  for image in all_images:
    image_ID = getImageID(conn, os.path.basename(image))
    if image_ID is not None:
      raise Exception('Image ' + str(image) + ' that is in import-list is in database already.')

  # Import directory
  uploadImages(all_images)

  # Add metadata
  add_plate_metadata(all_images, conn)


def add_plate_metadata(images, conn):
  logging.info("start add_plate_metadata")

  # sort images with image_name_sort_fn
  # makes sure well, wellsample and channels come sorted
  # after each other when looping the list
  sorted(images, key=image_name_sort_fn)

  # get meta from first image as a plate representative
  first_image_meta = parse_path_and_file(images[0])
  logging.debug(first_image_meta)
  plate_ID = getPlateID(conn, metadata['plate'])
  if plate_ID is not None:
     raise Exception('Plate ' + str(metadata['plate']) + ' that is about to be imported is in database already with ID:' + str(plate_ID))

  # Create Plate
  plate = omero.model.PlateI()
  plate.setName(rstring(first_image_meta['plate']))
  plate = conn.getUpdateService().saveAndReturnObject(plate)

  # Create PlateAquisition?
  aq_start_time = datetime.datetime(year = first_image_meta['date_year'],
                                    month = first_image_meta['date_month'],
                                    day = first_image_meta['date_day_of_month'])
  plateaq = omero.model.PlateAcquisitionI()
  plateaq.setName(rstring(first_image_meta['plate'] + '_' + str(aq_start_time)))
  plateaq.setPlate(plate)
  start_time_epoch = time.mktime(aq_start_time.timetuple())
  plateaq.setStartTime(rtime(start_time_epoch))
  plateaq.setEndTime(rtime(start_time_epoch))
  plateaq = conn.getUpdateService().saveAndReturnObject(plateaq)

  # Loop all Images
  well = None
  last_well_name = None
  wellsample = None
  for image in images:
    img_meta = parse_path_and_file(image)

    # Get Image reference fom database
    # we have to get it by query-service or otherwise properties are
    # not filled in and Error will be thrown later when image methods are used
    qs = conn.getQueryService()
    params = omero.sys.Parameters()
    params.map = {'imagename': rstring(os.path.basename(image))}
    logging.debug(params.map)
    # TODO change from findAllByQuery to findAllByQuery and only one return
    images = qs.findAllByQuery("from Image as i where i.name=:imagename", params)
    image = images[0]

    well_name = img_meta['well']
    # Create Well, only if the well-name is different from the last image well-name
    if well is None or last_well_name != well_name:
      well = omero.model.WellI()
      well.setExternalDescription(rstring(well_name))
      row_col = well_label2row_col(well_name)
      logging.info(row_col)
      well.setColumn(rint(row_col['col']))
      well.setRow(rint(row_col['row']))
      well.setPlate(plate)
      well = conn.getUpdateService().saveAndReturnObject(well)
      last_well_name = well_name

    # Create Wellsamples (one for each picture, each channel is stored as a separate wellsampla=
    wellsample_name = img_meta['wellsample']
    wellsample = omero.model.WellSampleI()
    wellsample.setImage(image)
    # wellsample.well = well
    wellsample.setPlateAcquisition(plateaq)
    logging.debug(wellsample_name)
    #wellsample.posX = omero.model.LengthI(rdouble(img_meta['wellsample']), omero.model.enums.UnitsLength.PIXEL)
    well.addWellSample(wellsample)
    wellsample = conn.getUpdateService().saveAndReturnObject(wellsample)

    # TODO create channel?

    # Add key value annotation to image
    map_ann = omero.gateway.MapAnnotationWrapper(conn)
    # Use 'client' namespace to allow editing in Insight & web
    namespace = omero.constants.metadata.NSCLIENTMAPANNOTATION
    map_ann.setNs(namespace)

    img_meta_as_map_ann = dictToMapAnnotation(img_meta)

    logging.debug(img_meta_as_map_ann)

    map_ann.setValue(img_meta_as_map_ann)
    map_ann.save()


    # NB: only link a client map annotation to a single object

    image_id = image.getId()
    image_v2 = conn.getObject("Image", image_id)
    logging.debug(image_v2)

    image_v2.linkAnnotation(map_ann)

#
#
#
#  Main entry for script
#
#
#
try:
  
  # 
  # Configure logging
  #
  #logging.basicConfig(level=logging.INFO)
  logging.getLogger("omero").setLevel(logging.WARNING)
  logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%H:%M:%S',
    level=logging.DEBUG)
    
  logging.info("Start script")

  proj_image_dir = "/share/mikro/IMX/MDC Polina Georgiev/exp-WIDE/"
  last_mod_date = getLastModificationInDir(proj_image_dir, '*')

  # Get connection to server
  conn = getOmeroConn()

  # Get all subdirs (these are the top plate dir)
  plate_dirs = get_subdirs(proj_image_dir)
  logging.debug("plate_dirs" + str(plate_dirs))
  for plate_dir in plate_dirs:
    plate_subdirs = get_subdirs(plate_dir)
    for plate_date_dir in plate_subdirs:
      logging.debug("plate_subdir: " + str(plate_date_dir))
      rel_plate_date_dir = relpath(plate_date_dir, proj_image_dir)
      
      # Parse filename for metadata (e.g. platename well, site, channet etc.)
      metadata = parse_path_plate_date(rel_plate_date_dir)
      logging.debug("metadata" + str(metadata))

      # Check if plate exists in database (if no - then import folder)
      #
      # TODO (and aquisition-date?)
      #
      # TODO create screen?
      #
      plate_ID = getPlateID(conn, metadata['plate'])
      if plate_ID is None:
        # import images and create database entries for plate, well, site etc.
        import_plate_images_and_meta(plate_date_dir, conn)

        # TODO annotate plate to screen

      else:
		    logging.info("Plate already in DB: " + metadata['plate']);
		    sys.exit("# Exit here")


finally:
  if conn is not None:
    conn.close()
    
  logging.info("Done script")
