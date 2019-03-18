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
#
# docker-compose up
# docker exec -it omero-server-dev bash
#
# Python path
# export PYTHONPATH=$PYTHONPATH:/home/anders/projekt/pharmbio/OMERO/dev/OMERO.server-5.4.10-ice36-b105/lib/python
# export PYTHONPATH=$PYTHONPATH:/opt/omero/server/OMERO.server/lib/python/
# export OMERO_DEV_PASSW=devpass
# /scripts/import-cli-version3.py


#import sys
#sys.path.append('/home/anders/projekt/pharmbio/OMERO/dev/OMERO.server-5.4.10-ice36-b105/lib/python')

import omero
import platform
import os
from omero.gateway import BlitzGateway
from omero.cli import cli_login
from omero.rtypes import rstring, rint
import logging
import sys
import cStringIO
import json
# from IPython.core.debugger import Tracer

def parse_json_result(text):
  json_out=[]
  logging.info("text" + text)
  if text != "":
    json_out = json.loads(text)

  debug=False
  if debug == True:
    print(json.dumps(json_out, indent=4, sort_keys=True))

  return json_out

def retval2id(text):
  retval = ""
  logging.info("text" + text)
  if text != "":
    array = text.split(":")
    id = array[1].strip()
    retval = id

  return retval

def execOmeroCommand(args):
  logging.info("exec command:" + str(args))
  stdout_ = sys.stdout
  redirected_stdout = cStringIO.StringIO()
  sys.stdout = redirected_stdout
  retval = ""

  password = os.environ['ROOTPASS']
  with cli_login("--server","localhost","--port", "4064", "--user","root", "--password", password ) as cli:
    logging.info("Before command")
    cli.invoke(args)
    logging.info("After command")
    retval = redirected_stdout.getvalue()
    cli.close()

  # restore stream
  sys.stdout = stdout_
  logging.info("retval " + retval)
  return retval


def searchOmero(object_type, searchterm):
  args = ["search",
            object_type,
            searchterm,
            "--field",
            "name",
            "--style",
            "json"
           ]
  searchresult = execOmeroCommand(args)

  return parse_json_result(searchresult)


def createObject(object_type, name):
  args = ["obj",
          "new",
          object_type,
          "name=" + name
          ]
  retval = execOmeroCommand(args)

  return retval2id(retval)

def getID(object_type, name):
  jsonlist = searchOmero(object_type, name)
  if len(jsonlist) > 0:
    return jsonlist[0]['Id']
  else:
    return None

def existsInDB(object_type, name):
  id = getID(object_type, name)
  print("id", id)
  if id is None:
    return False
  else:
	  return True

def getProjectID(name):
  return getID("Project", name)

def getDatasetID(name):
  return getID("Dataset", name)

def getImageID(name):
  return getID("Image", name)

def imageExists(name):
  return existsInDB("Image", name)

def projectExists(name):
  return existsInDB("Project", name)

def datasetExists(name):
  return existsInDB("Dataset", name)

def projectCreate(name):
  return createObject("Project", name)

def datasetCreate(name):
  return createObject("Dataset", name)

def getOrCreateProject(name):
  id = getProjectID(name)
  if id is None:
    id = projectCreate(name)
  return id

def getOrCreateDataset(name):
  id = getDatasetID(name)
  if id is None:
    id = datasetCreate(name)
  return id

def getOmeroConn():
  password = os.environ['ROOTPASS']
  conn = BlitzGateway("root", password, host="localhost", port="4064")
  conn.connect()
  return conn

def addMapAnnotation(imageID, key_value_data):
  conn = getOmeroConn()
  map_ann = omero.gateway.MapAnnotationWrapper(conn)
  # Use 'client' namespace to allow editing in Insight & web
  namespace = omero.constants.metadata.NSCLIENTMAPANNOTATION
  map_ann.setNs(namespace)
  map_ann.setValue(key_value_data)
  map_ann.save()

  fileToAnnotate = conn.getObject("Image", imageID)
  # NB: only link a client map annotation to a single object
  fileToAnnotate.linkAnnotation(map_ann)

  logging.info("Annotated OK")
  conn.close()

# Only return first id for now
def searchObj(obj_types, text, fields):
  conn = getOmeroConn()
  retval = None
  for i in conn.searchObjects(obj_types, text, fields):
    # print i.OMERO_CLASS, i.getName(), i.getId()
    retval = i.getId()
    break
  conn.close()
  return retval

def searchDS(name):
  return searchObj(["Dataset"], name, fields=("name",))

def searchScreen(name):
  return searchObj(["Screen"], name, fields=("name",))

def searchPlate(name):
  return searchObj(["Plate"], name, fields=("name",))

def searchWell(name):
  return searchObj(["Well"], name, fields=("externalDescription",))

def searchWellSample(name):
  return searchObj(["WellSample"], name, fields=("name",))

def createObj(obj, name):
  conn = getOmeroConn()
  obj.setName(rstring(name))
  obj = conn.getUpdateService().saveAndReturnObject(obj)
  obj_id = obj.id.getValue()
  conn.close()
  return obj_id

def createDataset(name):
  return createObj(omero.model.DatasetI(), name)

def createScreen(name):
  return createObj(omero.model.ScreenI(), name)

def createPlate(name):
  return createObj(omero.model.PlateI(), name)

def createWell(name, plateID):
  conn = getOmeroConn()
  obj = omero.model.WellI()
  obj.setExternalDescription(rstring(name))
  obj.setColumn(rint(0))
  obj.setRow(rint(0))
  plate = conn.getObject("Plate", plateID)
  obj.setPlate(omero.model.PlateI(plate.getId(), False))
  obj = conn.getUpdateService().saveAndReturnObject(obj)
  obj_id = obj.id.getValue()
  conn.close()
  return obj_id

def createWellSample(wellID, plateID, imageID):
  conn = getOmeroConn()

  image = omero.model.ImageI(imageID, False)
  plate = omero.model.PlateI(plateID, False)


  well = omero.model.WellI()
  well.plate = plate
  well.column = rint(1)
  well.row = rint(1)
  savedWell = conn.getUpdateService().saveAndReturnObject(well)

  ws = omero.model.WellSampleI()
  ws.setImage(image)
  #ws.image = omero.model.ImageI(image.id, False)
  ws.well = savedWell
  savedWell.addWellSample(ws)
  savedWS = conn.getUpdateService().saveAndReturnObject(ws)

  obj_id = savedWell.id.getValue()
  conn.close()
  return obj_id


#
# Filename examples
# 181214-KOday7- 40X- H2O2- Glu     _E02_s1_w14C0B5387-40BB-433A-9981-204DD0A2C244.tif
# 190131-U2OS-   20X- CopyAP009068 _B02_s4_w1602D3899-2E43-4530-8A73-2C1A8A49ED1E.tif
# 181212-ACHN-   20X- BpA- HD-DB-high  _B02_s8_w324263B43-90B5-4388-8D6C-B5B2EA8BE7C1.tif
#
def parseImagename(name):

  dash_split=name.split("-")
  undersc_split=name.split("_")

  project="proj_" + "exp_wide" # this is part of should be path
  dataset="ds_" + dash_split[1]
  screen="scr_" + dash_split[1]
  plate=dash_split[3]
  well=undersc_split[1]
  wellsample=undersc_split[2]
  channel_and_more=undersc_split[3]
  channel=channel_and_more[1]
  date=dash_split[0]
  magnification=dash_split[2]

  return {'project':project, 'dataset':dataset, 'screen':screen,
          'plate':plate, 'well':well, 'wellsample':wellsample,
          'channel':channel, 'date':date, 'magnification':magnification}

def uploadImage(filepath, datasetID):
  filename = os.path.basename(filepath)

  logging.info("datasetID="+ str(datasetID))

  args = ["import",
          "--quiet",
          "--transfer", "ln_s",
          "--skip","all",
          "-T", "Dataset:id:" + str(datasetID),
          filepath
          ]

  result = execOmeroCommand(args)

def linkDatasetToProj(datasetID, projectID):
  conn = getOmeroConn()
  project = conn.getObject("Project", projectID)
  link = omero.model.ProjectDatasetLinkI()
  link.setParent(omero.model.ProjectI(project.getId(), False))

  dataset = conn.getObject("Dataset", datasetID)
  link.setChild(omero.model.DatasetI(dataset.getId(), False))
  conn.getUpdateService().saveObject(link)
  conn.close()

def linkPlateToScreen(plateID, screenID):
  conn = getOmeroConn()
  screen = conn.getObject("Screen", screenID)
  plate = conn.getObject("Plate", plateID)
  link = omero.model.ScreenPlateLinkI()
  link.setParent(omero.model.ScreenI(screen.getId(), False))
  link.setChild(omero.model.PlateI(plate.getId(), False))
  conn.getUpdateService().saveObject(link)
  conn.close()

def linkWellToPlate(wellID, plateID):
  conn = getOmeroConn()
  plate = conn.getObject("Plate", plateID)
  well = conn.getObject("Well", screenID)
  link = omero.model.PlateWellLinkI()
  link.setParent(omero.model.PlateI(plate.getId(), False))
  link.setChild(omero.model.WellI(well.getId(), False))
  conn.getUpdateService().saveObject(link)
  conn.close()


#def linkPlateToScreen(plateID, screenID):
#  conn = getOmeroConn()
#  screen = conn.getObject("Screen", screenID)
#  plate = conn.getObject("Plate", plateID)
#  screen.linkPlate(plate)
#  conn.close()


def uploadImageUnique(imagefile):

  image_uploaded = False
  imageID = getImageID(imagefile)
  if imageID is None:
    print("Not Image exists")
    parsed_name = parseImagename(imagefile)
    logging.info(parsed_name)
    projID = getOrCreateProject(parsed_name['project'])
    datasetID = searchDS(parsed_name['dataset']) # getDatasetID(parsed_name['dataset'])
    plateID = searchPlate(parsed_name['plate'])
    screenID = None
    if datasetID is None:
      datasetID = createDataset(parsed_name['dataset'])
      logging.info(datasetID)
      linkDatasetToProj(datasetID, projID)
    imageID = uploadImage(imagefile, datasetID)

  else:
    logging.info("Image exists, ImageID=" + str(imageID))
    parsed_name = parseImagename(imagefile)
    screenID = searchScreen(parsed_name['screen'])
    if screenID is None:
      screenID = createScreen(parsed_name['screen'])
      logging.info(screenID)
    plateID = searchPlate(parsed_name['plate'])
    logging.info(plateID)
    if plateID is None:
      plateID = createPlate(parsed_name['plate'])
      logging.info(plateID)
      linkPlateToScreen(plateID, screenID)
    #wellID = searchWell(parsed_name['well'])
    #logging.info(wellID)
    #if wellID is None:
    #  wellID = createWell(parsed_name['well'], wellID)
    #  logging.info(wellID)
    wellID = 99
    wellID = createWellSample(wellID, plateID, imageID)
    logging.info(wellSampleID)


  annotation = [["key1", "value1"],
                ["key2", "value2"],
                ["key3", "value3"]]

  addMapAnnotation(imageID, annotation)




try:

  #logging.basicConfig(level=logging.INFO)
  logging.getLogger("omero").setLevel(logging.WARNING)
  logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%H:%M:%S',
    level=logging.INFO)
  logging.info("Start script")

  logging.info(os.environ["PYTHONPATH"])

  image_dir = "/share/mikro/IMX/MDC Polina Georgiev/exp-WIDE"
  for filename in os.listdir(image_dir):
    logging.info(filename)

    # Search for filename (path and file suffix not included in search)
    filepath = os.path.join(image_dir, filename)
    uploadImageUnique(filepath)


finally:
  logging.info("Done script")
