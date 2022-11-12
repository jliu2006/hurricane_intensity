from modis_tools.auth import ModisSession
from modis_tools.resources import CollectionApi, GranuleApi
from modis_tools.granule_handler import GranuleHandler
from glob import *
import json
import os
from pyhdf.SD import SD, SDC
import numpy as np
import sys

username_file = open("/home/fun/profile/modis_username.txt", "r")
password_file = open("/home/fun/profile/modis_password.txt", "r")
username = username_file.readline()
password = password_file.readline()

def convert_date(datestr):
    return datestr[0:4] + '-' + datestr[4:6] + '-' + datestr[6:8]

# def getTgtArea(rgb, lon, lat, radias):
#     n = 3600
#     m = 7200
    
#     interval = 180.0 / n
    
#     lat_index = int((90 - lat) / interval)
#     long_index = int((lon + 180) / interval)
    
#     n_raidus = int(radias / interval)
    
    
#     return rgb[lat_index - n_raidus:lat_index + n_raidus, long_index - n_raidus:long_index + n_raidus]
  


def download_file(folder, start_date, end_date, lon, lat, radius):

    print ('downloading ', start_date, end_date)
    # Authenticate a session
    session = ModisSession(username=username, password=password)

    # Query the MODIS catalog for collections
    collection_client = CollectionApi(session=session)

    collections = collection_client.query(short_name="MOD09CMG", version="006")
    
    # Query the selected collection for granules
    granule_client = GranuleApi.from_collection(collections[0], session=session)

    # Filter the selected granules via spatial and temporal parameters
    #comma-separated numbers: lower left longitude, lower left latitude, upper right longitude, upper right latitude.
    bounding_bbox = [lon-radius, lat-radius, lon+radius, lat+radius]
    print(bounding_bbox)
    
    h_granules = granule_client.query(start_date=start_date, end_date=end_date, bounding_box=bounding_bbox)
    
    # Download the granules
    GranuleHandler.download_from_granules(h_granules, session, path=folder)
        
    
def post_processing(folder, params):
    curr_files = glob(folder + "*.hdf", recursive = True)
    if len(curr_files) == 0:
        return
    curr_file = curr_files[0]
    
    print ('found ', curr_file)
    
    hdf = SD(curr_file) # first day of hurricane sandy

    for it in hdf.datasets():
        print (it)

    R = hdf.select('Coarse Resolution Surface Reflectance Band 1').get()
    B = hdf.select('Coarse Resolution Surface Reflectance Band 3').get()
    G = hdf.select('Coarse Resolution Surface Reflectance Band 4').get()

    R_true = R * 0.0001
    G_true = G * 0.0001
    B_true = B * 0.0001

    rgb = np.dstack([R_true, G_true, B_true])

    print (B.shape)

    lat = str(params['lt'])
    lon = str(params['lg'])
    lom = -1 if lon[-1] == 'W' else 1
    
    lat = lat[:-1]
    lon = lon[:-1]
    
    radius = 10
    
    area = getTgtArea(rgb, float(lon)*lom, float(lat), radius)
    
    filename = folder + str(radius) + '_modis_satellite_' + str(params['date']) + '.npy'
    
    np.save(filename, area)
    
    print ("removing ", curr_file)
    os.remove(curr_file)


def download_modis(folder):
    json_profile = folder + '/profile.json'
    json_file = open(json_profile)
    d = json.load(json_file)
    current_date = None
    for it in d['path']:
        print(it)
        # only download once per day as modis satelite is daily
        if it['date'] == current_date:
            continue
        current_date = it['date']        
        
        lat = str(it['lt'])
        lon = str(it['lg'])
        lom = -1 if lon[-1] == 'W' else 1

        lat = float(lat[:-1])
        lon = float(lon[:-1])
        
        download_file(folder, convert_date(str(it['date'])),  convert_date(str(it['date'])), lon * lom, lat,  10)
        
        #post_processing(folder, it)
        


print ('Number of arguments:', len(sys.argv), 'arguments.')
print ('Argument List:', str(sys.argv))

hurricanes_folders = glob("/home/fun/data/" + sys.argv[1] + "/", recursive = True)

for it in hurricanes_folders:
    print (it)
    download_modis(it)
