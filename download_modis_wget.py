from glob import *
import json
import os
from pyhdf.SD import SD, SDC
import numpy as np
import sys
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import re
import csv

username_file = open("/home/fun/profile/modis_username.txt", "r")
password_file = open("/home/fun/profile/modis_password.txt", "r")
username = username_file.readline()
password = password_file.readline()

def convert_date(datestr):
    return datestr[0:4] + '-' + datestr[4:6] + '-' + datestr[6:8]

def getTimeIndex(lon, lat):
    n = 3600
    m = 7200

    interval = 180.0 / n

    lat_index = int((90 - lat) / interval)
    long_index = int((lon + 180) / interval)
    
    return long_index, lat_index

def getTgtArea(rgb, lon, lat, radias):
    n = 3600
    m = 7200
    
    interval = 180.0 / n
    
    lat_index = int((90 - lat) / interval)
    long_index = int((lon + 180) / interval)
    
    n_raidus = int(radias / interval)
    
    
    return rgb[lat_index - n_raidus:lat_index + n_raidus, long_index - n_raidus:long_index + n_raidus]
  
def getNearestIndex(array, value):
    idx = (np.abs(array - value)).argmin()
    return idx

def getScaleFactor(small_time, large_time, target_time): # coefficient of multiplication for lin interpolation
    delta_time = large_time - small_time
    delta_target = target_time - small_time
    scale_factor = delta_target/delta_time
    return scale_factor

def coordSTRtoFLOAT(lat, lon): # called in linearInterpolation, shape (2,), lat first then lon
    lat = str(lat)
    lon = str(lon)
    lom = -1 if lon[-1] == 'W' else 1

    lat = float(lat[:-1])
    lon = float(lon[:-1])
    lon = lon * lom
    
    return lat, lon


def linearCalculation(scale_factor, small_coords, large_coords): # coords passed as shape (2,)

    sm_lat, sm_lon = coordSTRtoFLOAT(small_coords[0], small_coords[1])
    lg_lat, lg_lon = coordSTRtoFLOAT(large_coords[0], large_coords[1])
    
    delta_lat = lg_lat - sm_lat
    delta_lon = lg_lon - sm_lon
    
    scale_lat = delta_lat * scale_factor
    scale_lon = delta_lon * scale_factor
    
    interp_lat = scale_lat + sm_lat
    interp_lon = scale_lon + sm_lon
    
    return interp_lat, interp_lon

def wrappedLinearInterpolation(profile, day, selected_time):
    print(day, selected_time)
    early_times = []
    early_coords = []
    late_times = []
    late_coords = []
    paths = profile['path']
    
    for path in paths:
        if path['date'] == int(day):
            path_time_hour = float(path['time'])/60
            print(path_time_hour)
            if path_time_hour <= selected_time:
                print('early', path_time_hour)
                early_times = np.append(early_times, path_time_hour)
                early_coords = np.append(early_coords, (path['lt'], path['lg']))
                early_coords = early_coords.reshape(int(len(early_coords)/2), 2)
            else:
                print('late', path_time_hour)
                late_times = np.append(late_times, path_time_hour)
                late_coords = np.append(late_coords, (path['lt'], path['lg']))
                late_coords = late_coords.reshape(int(len(late_coords)/2), 2)
    early_index = getNearestIndex(early_times, selected_time)
    late_index = getNearestIndex(late_times, selected_time)

    scale_factor = getScaleFactor(early_times[early_index], late_times[late_index], selected_time)

    new_lat, new_lon = linearCalculation(scale_factor, early_coords[early_index], late_coords[late_index])

    return new_lon, new_lat
    
    
def post_processing(folder, params, day):
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
    time = hdf.select('Coarse Resolution Granule Time').get()

    R_true = R * 0.0001
    G_true = G * 0.0001
    B_true = B * 0.0001

    rgb = np.dstack([R_true, G_true, B_true])

    print (B.shape)
    
    paths = params['path']
    
    for path in paths:
        if path['date'] == int(day):
            break
    
    lat, lon = coordSTRtoFLOAT(path['lt'], path['lg'])
    radius = 10
    long_index, lat_index = getTimeIndex(lat, lon)
    selected_time = (time[lat_index, long_index])/60
    
    new_lon, new_lat = wrappedLinearInterpolation(params, day, selected_time)
    
    area = getTgtArea(rgb, new_lon, new_lat, radius)
    
    filename = folder + str(radius) + '_modis_satellite_' + str(path['date']) + '.npy'
    
    np.save(filename, area)
    
    print ("removing ", curr_file)
    os.remove(curr_file)
   
    
def download_file(folder, url, filename):
     
    username_file = open("/home/fun/profile/modis_username.txt", "r")
    password_file = open("/home/fun/profile/modis_password.txt", "r")
    username = username_file.readline()
    password = password_file.readline()
    
    url = url + filename
    if len(filename) == 0:
        filename = 'modis_index.html'
    
    print ('downloading file ', url)
    
    r = requests.get(url, auth = (username, password))
    if r.status_code == 200:
        print ('writing to', folder + filename)
        with open(folder + filename, 'wb') as out:
            for bits in r.iter_content():
                out.write(bits)
    else:
        print ('download error ', r.status_code)
        
def parse_html(html_file):
    '''
    parse html to get file list
    '''       
    fl = glob(html_file)
    if len(fl) == 0:
        return []
   
    with open(html_file, 'r') as input:
        soup = BeautifulSoup(input, "html.parser").find_all(lambda t: t.name == "a" and t.text.startswith('MOD') and t.text.endswith('hdf'))
        filelist = []
        for it in soup:
            filelist.append(it["href"])
        return filelist
    
def generate_modis_url(datestr):
    '''
    compose url using date  'YYYY.MM.DD'
    '''
    url = 'https://e4ftl01.cr.usgs.gov/MOLT/MOD09CMG.006/'+ datestr[0:4] + '.' + datestr[4:6] + '.'+ datestr[6:8] + '/'
    
    return url
    

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
        print("current date:", current_date)
        
        lat = str(it['lt'])
        lon = str(it['lg'])
        lom = -1 if lon[-1] == 'W' else 1

        lat = float(lat[:-1])
        lon = float(lon[:-1])
        
 
        url = generate_modis_url(str(current_date))
        print (url)
        download_file(folder, url, "")

        filelist = parse_html(folder + 'modis_index.html')

        if len(filelist) > 0:
            print ('downloading ', filelist[0], 'to ', folder)
            download_file(folder, url, filelist[0])
        
        post_processing(folder, d, current_date)
        


print ('Number of arguments:', len(sys.argv), 'arguments.')
print ('Argument List:', str(sys.argv))

hurricanes_folders = glob("/home/fun/data/" + sys.argv[1] + "/", recursive = True)

folder = '/home/fun/data/AL182012'
json_profile = folder + '/profile.json'
json_file = open(json_profile)
d = json.load(json_file)

for it in hurricanes_folders:
    print (it)
    download_modis(it)
    #post_processing(it, d, 20121024) 
