#!/usr/bin/env python2

# Code inspiration:
# Code from: https://gist.github.com/will-moore/f5402e451ea471fd05893f8b38a077ce
# from http://www.openmicroscopy.org/community/viewtopic.php?f=6&t=8407
# Uses code from https://github.com/openmicroscopy/openmicroscopy/blob/develop/components/tools/OmeroPy/src/omero/testlib/__init__.py

# https://docs.openmicroscopy.org/omero/5.4.10/users/cli/containers-annotations.html
# https://docs.openmicroscopy.org/omero/5.4.10/developers/Python.html

# API:
# https://downloads.openmicroscopy.org/omero/5.4.10/api/python/
#
# https://docs.openmicroscopy.org/omero/5.4.10/developers/Model/EveryObject.html#omero-model-class-wellsample
#
#
# docker-compose up
# docker exec -it omero-server-dev /scripts/import-images-omero-v1.py
# docker exec -it omero-server-dev /scripts/import_screen_bulk.sh
# docker exec -it omero-server-dev /scripts/import_screen_pattern.sh
#
# Python path
# export PYTHONPATH=$PYTHONPATH:/home/anders/projekt/pharmbio/OMERO/dev/OMERO.server-5.4.10-ice36-b105/lib/python
# export PYTHONPATH=$PYTHONPATH:/opt/omero/server/OMERO.server/lib/python/
# export OMERO_DEV_PASSW=devpass
# /scripts/import-images-omero-v1.py
#
# Enter docker images
# docker exec -it omero-server-dev bash
# docker exec -it omero-postgres-dev bash -c 'psql -U postgres'
#
# CLI examples:
#
# /opt/omero/server/OMERO.server/bin/omero search Plate "P00904*"
#
# /opt/omero/server/OMERO.server/bin/omero import --bulk P009041_bulk.yml --server localhost --port 4064 --user root --password devpass
#
#
#  sudo shfs anders@130.238.44.3:/share/mikro /share/mikro -o allow_other -o ro
#

import platform
import os
from os.path import relpath
import re
import datetime
import time
import fnmatch
import logging
import traceback
import sys
import cStringIO
import json
import yaml

import omero
from omero.gateway import BlitzGateway
from omero.cli import cli_login
from omero.rtypes import rstring, rint, rdouble, rtime

# read password from environment
omero_rootpass = os.environ['ROOTPASS']

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
                            + '([A-Z0-9]{8}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12})'  # Image GUID [11]
                            + '(\.tiff?)?'  # Extension [12]
                            + '$'
                            ,
                            re.IGNORECASE)  # Windows has case-insensitive filenames

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
    'guid': match.group(11),
    'extension': match.group(12),
    'image_name': (match.group(4) + '-' +
                   match.group(5) + '-' +
                   match.group(6) + '_' +
                   match.group(7) + '_s' +
                   match.group(8)),
    'sort_string':(match.group(4) + '-' +
                   match.group(5) + '-' +
                   match.group(6) + '_' +
                   match.group(7) + '_s' +
                   match.group(8).zfill(2) + '_w' +
                   match.group(9).zfill(2)),

  }

  return metadata

#
# Adopted from: https://github.com/HASTE-project/haste-image-analysis-container2/tree/master/haste/image_analysis_container2/filenames
# path example
# 'ACHN-20X-P009060/2019-02-19/and-more/not/needed/'
__pattern_path_plate_date = re.compile('^'
                            + '.*'         # any
                            + '/([^-/]+)'  # screen-name (1)
                            + '-([^-/]+)'  # magnification (2)
                            + '-([^/]+)'   # plate (3)
                            + '/([0-9]{4})-([0-9]{2})-([0-9]{2})' # date (yyyy, mm, dd) (4,5,6)
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
    'date_year': int(match.group(4)),
    'date_month': int(match.group(5)),
    'date_day_of_month': int(match.group(6)),
  }

  return metadata


#
# Executes a command with the omero-cli program /opt/omero/server/OMERO.server/bin/omero
# Method redirects stdout so return values on stdout can be read in Python
#
def execOmeroCommand(args):
  logging.info("exec command:" + str(args))

  with cli_login("--server","localhost","--port", "4064", "--group", "pharmbio_read_annotate", "--user","root", "--password", omero_rootpass ) as cli:
    logging.info("Before command")
    cli.invoke(args)
    logging.info("After command")
    cli.close()

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

  execOmeroCommand(args)

#
# From a list of files/directories instead of a single file/directory
#
def uploadImages(file_list):

  for filepath in file_list:
    filename = os.path.basename(filepath)
    uploadImage(filepath)

#
# Performs a --bulk import
# Uses omero-cli program /...server.../bin/omero
#
def upload_images_bulk(bulk_import_file):

  args = ["import",
          "--quiet",
          "--skip", "minmax",
          "--bulk",
          bulk_import_file
          ]

  execOmeroCommand(args)

#
# Create a connection to server (This is for commands that are executed
# direct with python API and not via the /bin/omero command line client)
#
def getOmeroConn():
  try:
    conn = BlitzGateway("root", omero_rootpass, group="pharmbio_read_annotate", host="localhost", port="4064")
    conn.connect()
    return conn
  except Exception as e:
    logging.error("Something went wrong when getting OMERO-connection, is server up? Somethimes it takes 30 sek to start.")
    logging.error("Exception: " + str(e))
    raise e

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

def getImageIDNewConn(name):
  conn = None
  try:
    conn = getOmeroConn()
    logging.debug("name:" + str(name))
    id = getImageID(conn, name)
    logging.debug("id:" + str(id))
    return id
  finally:
    if conn is not None:
      conn.close()

#
# Throws Exception if more than one result is found
#
def getPlateID(conn, name):
  return getID(conn, "Plate", name, "name")

#
# Searches and opens a new connection for search instead
# of an already opened connection
#
# Throws Exception if more than one result is found
#
def getPlateIDNewConn(name):
  conn = None
  try:
    conn = getOmeroConn()
    id = getPlateID(conn, name)
    return id
  finally:
    if conn is not None:
      conn.close()

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
def get_subdirs(root_path, filter=""):
  subdirs = []
  for name in os.listdir(root_path):
    if filter in name:
      if os.path.isdir(os.path.join(root_path, name)):
        subdirs.append(os.path.join(root_path, name))
  return subdirs

#
# Recursively gets all (valid) imagefiles in subdirs
# e.g. *.tif, jpg and not *thumb"
#
def get_all_valid_images(path):
  # get all files
  all_files = recursive_glob(path, '*')

  # filter the ones we want
  pattern_file_filter = re.compile('^(?!.*thumb)(?=.*tif|.*jpg)') # not "thumb" but contains tif or jpg
  filtered_files = filter(pattern_file_filter.match, all_files)

  return filtered_files


#
# Return row and col index as integer from well label, e.g. 'A07'  becomes row:1,col:7
#
def well_label2row_col(label):
  row = ord(label[0].lower()) - 96 # 97 is character a in ascii ans
  col = int(label[1] + label[2])
  row_col = {
    'row': row,
    'col': col
  }
  return row_col

#
# Creates a Map in Omero preferred Annotation format from a dict
#
def dictToMapAnnotation(d):
  map_ann = []
  for key, value in d.iteritems():
    # values has to be string for omero
    key_val = [key, str(value)]
    map_ann.append(key_val)
  return map_ann

#
# Sorting iamge names needs to be done on metadata 'sort_string'
# because of site and channel that need to
# have values with leading 0 to be sorted correct
#
def image_name_sort_fn(filename):
  metadata = parse_path_and_file(filename)
  return metadata['sort_string']

#
# Returns true if any of files in list is in database already
#
def is_image_in_db(images):
  conn = None
  try:
    images_uploaded = False
    conn = getOmeroConn()
    for image in images:
      img_meta = parse_path_and_file(image)
      image_ID = getImageID(conn, img_meta['image_name'])
      if image_ID is not None:
        # TODO fix this a little bit more beautiful
        #raise Exception('Image ' + str(image) + ' that is in import-list is in database already.')
        images_uploaded = True
    return images_uploaded;
  finally:
    if conn is not None:
      conn.close()

def add_plate_metadata(images):
  logging.info("start add_plate_metadata")

  conn = None

  try:

    # sort images with image_name_sort_fn
    # makes sure well, wellsample and channels come sorted
    # after each other when looping the list
    images.sort(key=image_name_sort_fn)

    # Get one connection to be used during whole plate operation
    conn = getOmeroConn()

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
    image_name = None
    last_image_name = None
    well = None
    last_well_name = None
    wellsample = None
    for image in images:
      img_meta = parse_path_and_file(image)

      image_name = img_meta['image_name']
      if image_name is None or last_image_name != image_name:
        # Get Image reference fom database
        # we have to get it by query-service or otherwise properties are
        # not filled in and Error will be thrown later when image methods are used
        qs = conn.getQueryService()
        params = omero.sys.Parameters()
        params.map = {'imagename': rstring(image_name)}
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
          well.setColumn(rint(row_col['col'] - 1)) # row and col is 0 index in omero
          well.setRow(rint(row_col['row'] - 1)) # row and col is 0 index in omero
          well.setPlate(plate)
          well = conn.getUpdateService().saveAndReturnObject(well)
          last_well_name = well_name
        else:
          well = conn.getObject("Well", well.id.val)
          # Force WellWrapper to load wellsamples for this well
          well._listChildren()
          # we want the wrapped omero.model.WellI object
          well = well._obj

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

        last_image_name = image_name
  finally:
    if conn is not None:
      conn.close()

#
#
# ACHN-20X-P009060_G11_s9_w52B1ACE5F-5E6A-4AEC-B227-016795CE2297.tif
#
def create_image_import_pattern_files(plate_date_dir, pattern_plate_date_dir, images):
  logging.info("start create_image_import_pattern_files" + plate_date_dir)

  # sort images with image_name_sort_fn
  # makes sure well, wellsample and channels come sorted
  # after each other when looping the list
  images.sort(key=image_name_sort_fn)

  # Loop all Images
  wellsample = None
  last_wellsample = None
  channel_and_uuid = []
  for image in images:
    img_meta = parse_path_and_file(image)
    wellsample = img_meta['wellsample']

    # For each wellsample(site) create a pattern file with all channels
    # Clear and start over with new uuid
    if wellsample is None or last_wellsample != wellsample:
      # start over with new uuids
      channel_and_uuid = []
      logging.info("channel_and_uuid:" + str(channel_and_uuid))

    channel_and_uuid.append(str(img_meta['color_channel']) + img_meta['guid'])


    # create patterns file name by replacing root dir with rootdir + patterns_subdir
    pattern_file_path = str(os.path.dirname(image)).replace(plate_date_dir, pattern_plate_date_dir)

    logging.debug("pattern_file_path:" + str(pattern_file_path))

    #
    pattern_file_name = img_meta['image_name'] + ".pattern"

    pattern_file = os.path.join(pattern_file_path, pattern_file_name)

    logging.debug("pattern_file:" + str(pattern_file))

    #
    image_path = str(os.path.dirname(image))
    pattern = (image_path + "/" +
               img_meta['image_name'] +
               "_w<" + ",".join(sorted(channel_and_uuid)) + ">" + img_meta['extension'] )


    # Create dir if not there
    if not os.path.exists(os.path.dirname(pattern_file)):
      os.makedirs(os.path.dirname(pattern_file))
    with open(pattern_file, 'w') as f:
      f.write(pattern)

    last_wellsample = wellsample

def create_bulk_import_file(pattern_plate_date_dir):
  logging.info("start create bulk file")
  pattern_files = recursive_glob(pattern_plate_date_dir, '*.pattern')
  pattern_files_tsv = os.path.join(pattern_plate_date_dir, "pattern_files.tsv")
  bulk_import_file = os.path.join(pattern_plate_date_dir, "bulk_import.yml")

  with open(pattern_files_tsv, 'w') as f:
    for pattern_file in pattern_files:
      image_name = os.path.splitext(os.path.basename(pattern_file))[0]
      line = '{name}\t{path}\n'.format(name=image_name, path=pattern_file)
      f.write(line)

  #  bulk_yml = ( '---' + '\n' +
  #               'transfer: = "ln_s"' + '\n' +
  #               'checksum_algorithm: "File-Size-64"' +
  #               'path: "/scripts/P009041.tsv"

  bulk_yml = dict(transfer = 'ln_s',
                  checksum_algorithm = 'File-Size-64',
                  path = pattern_files_tsv,
                  parallel_fileset = '2',
                  parallel_upload = '8',
                  columns = [
                            'name',
                            'path'
                            ]
                 )

  with open(bulk_import_file, 'w') as f:
    yaml.dump(bulk_yml, f, default_flow_style=False)

  return bulk_import_file

#
# Main import function that calls methods that will:
#
# 1. create pattern files for importing all channels as one fileset (vieved as one image in omero)
# 2. create bulk import file that imports all images via the pattern files
# 3. annotate images in database with plate, well, site info
#
def import_plate_images_and_meta(plate_date_dir, pattern_plate_date_dir):
  logging.debug("start import_plate_images_and_meta:" + str(plate_date_dir))
  all_images = get_all_valid_images(plate_date_dir)

  # Check that no image is in database already
  images_uploaded = is_image_in_db(all_images)
  if images_uploaded == False:
    # Create pattern and bulk import files
    create_image_import_pattern_files(plate_date_dir, pattern_plate_date_dir, all_images)
    bulk_import_file = create_bulk_import_file(pattern_plate_date_dir)

    # Import directory
    upload_images_bulk(bulk_import_file)

  # Add metadata
  add_plate_metadata(all_images)

#
#  Main entry for script
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
  fileHandler = logging.FileHandler("/scripts/import-omero.log", 'w')
  mylogformatter = logging.Formatter('%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')
  fileHandler.setFormatter(mylogformatter)
  rootLogger = logging.getLogger()
  rootLogger.addHandler(fileHandler)

  logging.info("Start script")

  #
  #
  # Testing
  #
  #
  #testdir = "/share/mikro/IMX/MDC Polina Georgiev/exp-WIDE/ACHN-20X-P009060/2019-02-19/51/ACHN-20X-P009060_G11_s10_w52B1ACE5F-5E6A-4AEC-B227-016795CE2297.tif"
  #retval = parse_path_plate_date(testdir)
  #logging.debug("retval" + str(retval))
  #logging.debug("wellsample:" + str(retval['wellsample']))
  #logging.debug("sort:" + str(retval['sort_string']))
  #sys.exit("exit here")

  #
  # End testing
  #
  #

  proj_root_dir = "/share/mikro/IMX/MDC Polina Georgiev/exp-WIDE/"
  plate_filter = "MCF7"
  pattern_root_dir = "/share/mikro_testdata/IMX/MDC Polina Georgiev/import_patterns/exp-WIDE/"

  # last_mod_date = getLastModificationInDir(proj_root_dir, '*')

  # Get all subdirs (these are the top plate dir)
  plate_dirs = get_subdirs(proj_root_dir)
  logging.debug("plate_dirs" + str(plate_dirs))
  for plate_dir in plate_dirs:
    # filter plate for names
    if plate_filter in plate_dir:
      plate_subdirs = get_subdirs(plate_dir)
      for plate_date_dir in plate_subdirs:
        logging.debug("plate_subdir: " + str(plate_date_dir))

        # create patterns dir name by replacing root dir with patterns root dir
        pattern_plate_date_dir = str(plate_date_dir).replace(proj_root_dir, pattern_root_dir)

        # Parse filename for metadata (e.g. platename well, site, channet etc.)
        metadata = parse_path_plate_date(plate_date_dir)
        logging.debug("metadata" + str(metadata))

        # Check if plate exists in database (if no - then import folder)
        #
        # TODO create screen? Add to correct group, permissions?
        #
        plate_ID = getPlateIDNewConn(metadata['plate'])
        if plate_ID is None:
          # import images and create database entries for plate, well, site etc.
          import_plate_images_and_meta(plate_date_dir, pattern_plate_date_dir)

          # TODO annotate plate to screen

        else:
          logging.info("Plate already in DB: " + metadata['plate']);
          #sys.exit("# Exit here")

except Exception as e:
  print(traceback.format_exc())

  logging.info("Done script")
