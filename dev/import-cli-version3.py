#!/usr/bin/env python2

#
# Code from: https://gist.github.com/will-moore/f5402e451ea471fd05893f8b38a077ce
# from http://www.openmicroscopy.org/community/viewtopic.php?f=6&t=8407
# Uses code from https://github.com/openmicroscopy/openmicroscopy/blob/develop/components/tools/OmeroPy/src/omero/testlib/__init__.py

# API
# https://downloads.openmicroscopy.org/omero/5.4.10/api/python/
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
import logging
import sys
import cStringIO
import json

def parse_json_result(text):
  json_out=[]
  if text != "":
    json_out = json.loads(text)
  
  debug=False
  if debug == True:
    print(json.dumps(json_out, indent=4, sort_keys=True))
    
  return json_out

def execOmeroCommand(args):
  stdout_ = sys.stdout
  redirected_stdout = cStringIO.StringIO()
  sys.stdout = redirected_stdout
	
  password = os.environ['OMERO_DEV_PASSW']
  with cli_login("--server","localhost","--port", "4064", "--user","root", "--password", password ) as cli:

    cli.invoke(args)
      
    # restore stream
    sys.stdout = stdout_
    
    retval = redirected_stdout.getvalue()
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
          "name=" + name,
          "--style",
          "json"
          ]  
  retval = execOmeroCommand(args)
  
  return parse_json_result(retval)
  
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

def imageExists(name):
  return existsInDB("Image", name)
  
def projectExists(name):
  return existsInDB("Project", name)
  
def datasetExists(name):
  return existsInDB("Dataset", name)
  
def parseImagename(name):
  # Filename examples
  # 181214-KOday7- 40X- H2O2- Glu     _E02_s1_w14C0B5387-40BB-433A-9981-204DD0A2C244.tif
  # 190131-U2OS-   20X- CopyAP009068 _B02_s4_w1602D3899-2E43-4530-8A73-2C1A8A49ED1E.tif
  # 181212-ACHN-   20X- BpA- HD-DB-high  _B02_s8_w324263B43-90B5-4388-8D6C-B5B2EA8BE7C1.tif
  
  dash_split=name.split("-")
  undersc_split=name.split("_")
  
  project="proj_" + dash_split[1]
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
         
def uploadImage(filepath):
  filename = os.path.basename(filepath)
  parsed_name = parseImagename(filename)
  
  print(parsed_name)
  
  #            ["import",
  #             "--quiet",
  #             "--transfer", "ln_s",
  #             "--skip","all",
  #             "-T", "Dataset:name:New-Dataset",
  #             filepath]
  # 
  # 
  # execOmeroCommand(args):
  

def uploadImageUnique(imagefile):
  image_uploaded = False
  if not imageExists(imagefile):
    print("Not Image exists")
    parsed_name = parseImagename(imagefile)
    uploadImage(imagefile)
  else:
    print("Image exists")
 

try:

  logging.basicConfig()
  print ("Start script")
  
  # stdout_ = sys.stdout
  # 
  # stream = cStringIO.StringIO()
  # #
  # # Call other method writing out
  # #
  # sys.stdout = stdout_ # restore the previous stdout.
  # variable = stream.getvalue() # get the other method stdout

  print(os.environ["PYTHONPATH"])
#  password = os.environ['OMERO_DEV_PASSW']
#  with cli_login("--server","localhost","--port", "4064", "--user","root", "--password", password ) as cli:
#    
#    
#    uploadImageUnique(
#    
#    cli.invoke("import --help")
#
#    args = ["--quiet",
#            "obj",
#            "new",
#            "Project",
#            "name=NewImages"
#           ]
#    retval = cli.invoke(args)
#    cli.out("Hello")
#    print("retval=", retval)
#    
#        
#    args = ["search",
#            "Project",
#            "NewImages",
#            "--style",
#            "json",
#           ]
#    retval = cli.invoke(args)
#    print("retval=", retval)
#    
#    args = ["search",
#            "Image",
#            "181214*",
#            #"--style",
#            #"json",
#           ]
#    retval = cli.invoke(args)
#    print("retval=", retval)
    
    
   
  image_dir = "/share/mikro/IMX/"
  for filename in os.listdir(image_dir):
    print filename
    
    # Search for filename (path and file suffix not included in search)
    filepath = os.path.join(image_dir, filename)
    uploadImageUnique(filepath)
   
    #args = ["import",
    #         "--quiet",
    #         "--transfer", "ln_s",
    #         "--skip","all",
    #         "-T", "Dataset:name:New-Dataset",
    #         filename]
    #
    #retval = cli.invoke(args)
    #print("retval=", retval)

  ## Put the images into a Dataset
  #DATASET = 52
  #links = []
  #for p in rsp.pixels:
  #    print ('Looping the Imported Images, ID:', p.image.id.val)
  #    link = omero.model.DatasetImageLinkI()
  #    link.parent = omero.model.DatasetI(DATASET, False)
  #    link.child = omero.model.ImageI(p.image.id.val, False)
  #    links.append(link)

  #conn.getUpdateService().saveArray(links, conn.SERVICE_OPTS)

finally:
  print ("Done script")
