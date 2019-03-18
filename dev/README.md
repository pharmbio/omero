# Development setup for our OMERO-server python 2.7 scripts

Start development version of omero-server, omero-web, and postgres

     docker-compose up -d
     
The folder `../share/mikro/` (with a small test-dataset of images is bind-mounted to the omero-server container)
     
Edit scripts as you please

     vim import-images-omero-v1.py
     
Run script from within the omero-server docker-container
The present working directory (PWD) is mounted inside the omero-server- 
container as `/scripts` 
This makes all edits in the `./import-images-omero-v1.py` reflected inside omero-server container

     docker exec -it omero-server-dev /scripts/import-images-omero-v1.py
     
Web-GUI for OMERO (OMERO-web)

     # OBS Sometimes it is difficult to connect, I don't exactly know why
     # It might be that it takes some minutes for web-server to be ready?
     #
     # I have noted that it is good to try both 127.0.0.1 and localhost, or your current ip
     #

     http://127.0.0.1:4080
     
     http://localhost:4080
     
     http://<your current ip>:4080

