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
import random

username_file = open("/home/fun/profile/modis_username.txt", "r")
password_file = open("/home/fun/profile/modis_password.txt", "r")
username = username_file.readline()
password = password_file.readline()


def timeToHours(now):
    now = str(now).zfill(4)
    print(now)
    hours = int(now[0:2]) + int(now[2:])/60
    return hours
    

def convert_date(datestr):
    return datestr[0:4] + '-' + datestr[4:6] + '-' + datestr[6:8]

def getTimeIndex(lon, lat):
    n = 3600
    m = 7200

    interval = 180.0 / n

    lat_index = int((90 - int(lat)) / interval)
    long_index = int((int(lon) + 180) / interval)
    
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


def linearCalculation(scale_factor, small_coords, large_coords): # coords passed as shape (2,), lat, lon

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
    
    paths = profile['path']
    paths_in_day = []
    for path in paths:
        if path['date'] == int(day):
            paths_in_day.append(path)
    
    print(day, selected_time)
    late_idx = 0
    paths = profile['path']
    

    while late_idx < len(paths_in_day):
        it = paths_in_day[late_idx]
        print(it, it['time'])
        path_time_hour = it['time']
        path_time_hour = timeToHours(path_time_hour)
        if path_time_hour >= selected_time:
            print('late', path_time_hour)
            break    
        late_idx += 1

    if late_idx == len(paths_in_day): # all time stamps happen before selected_time
        new_lon = paths_in_day[late_idx-1]['lg']
        new_lat = paths_in_day[late_idx-1]['lt']
        new_lat, new_lon = coordSTRtoFLOAT(new_lat, new_lon)
        return new_lon, new_lat
    elif late_idx == 0:
        new_lon = paths_in_day[late_idx]['lg']
        new_lat = paths_in_day[late_idx]['lt']
        new_lat, new_lon = coordSTRtoFLOAT(new_lat, new_lon)
        return new_lon, new_lat
    
    early_step = paths_in_day[late_idx-1]
    late_step = paths_in_day[late_idx]
    
    early_time = early_step['time']
    late_time = late_step['time']
    scale_factor = getScaleFactor(timeToHours(early_time), timeToHours(late_time), selected_time)
    
    early_coords = coordSTRtoFLOAT(early_step['lt'], early_step['lg'])
    late_coords = coordSTRtoFLOAT(late_step['lt'], late_step['lg'])

    new_lat, new_lon = linearCalculation(scale_factor, early_coords, late_coords)

    return new_lon, new_lat

def neighborRGB(color):
    for row in range(len(color)):

        found_swath = False
        swath_start = 0
        len_swath = 0
        idx = 0

        curr_row = color[row]
        
        while idx < len(curr_row):
            
            if found_swath == True:
                if curr_row[idx][0] != -2.8672 or curr_row[idx][1] != -2.8672 or curr_row[idx][2] != -2.8672:
                    found_swath = False
                else:
                    len_swath += 1
            elif curr_row[idx][0] == -2.8672  and curr_row[idx][1] == -2.8672 and curr_row[idx][2] == -2.8672:
                found_swath = True
                len_swath = 1
                swath_start = idx
            idx += 1

        existing_vals = []

        left_length = max(1,int(len_swath/2))
        right_length = max(1,int(len_swath - left_length))
        swath_end = swath_start + len_swath + 1
        #print("left:",left_length, "right:", right_length, "swath start:", swath_start)
        
        extra_right = max(0, swath_end+right_length - len(curr_row))
        left_length += extra_right
        
        extra_left = max(0, left_length - swath_start)
        right_length += extra_left

        existing_vals = np.append(existing_vals, curr_row[swath_start-left_length:swath_start])
        existing_vals = np.append(existing_vals, curr_row[swath_end:swath_end+right_length])
        
        
        for new_row_idx in (idx+1, idx+10):
            if new_row_idx >= 0 and new_row_idx < len(color):  # add previous row
                new_row = color[new_row_idx]
                for i in range(swath_start-left_length, swath_start):
                    if i >=0 and i < len(new_row):
                        if new_row[i][0] != -2.8672 or new_row[i][1] != -2.8672 or new_row[i][2] != -2.8672:
                            existing_vals = np.append(existing_vals, new_row[i])
                            
                for i in range(swath_end, swath_end+right_length+1):
                    if i >=0 and i < len(new_row):
                        if new_row[i][0] != -2.8672 or new_row[i][1] != -2.8672 or new_row[i][2] != -2.8672:
                            existing_vals = np.append(existing_vals, new_row[i])
        
        for idx in range(len_swath):
            if len(existing_vals) > 0:
                rand_idx = random.randint(0, len(existing_vals)-1)
                curr_row[swath_start+idx] = existing_vals[rand_idx]
    
def post_processing(folder, params, day):
    radius = 10
    
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
    
    paths_in_day = []
    best_time_diff = float('inf')
    selected_time = None
    for path in paths:
        if path['date'] == int(day):
            paths_in_day.append(path)            
    
    for it in paths_in_day:
        
        lat, lon = coordSTRtoFLOAT(it['lt'], it['lg'])
        long_index, lat_index = getTimeIndex(lon, lat)
        
        pick_time = time[lat_index, long_index]
        print('checking time in satelite', pick_time, 'with', it['time'])
        if pick_time == '0.0':
            rgb_select = getTgtArea(time, lon, lat, radius)
            rgb_select = rgb_select.flatten()
            pick_time = rgb_select[np.nonzero(rgb_select)].mean()
            print ('time in swath gap, use avg', pick_time)
            
        pick_time = timeToHours(pick_time)
        it_time = timeToHours(it['time'])
        time_diff = abs(pick_time - it_time)
        
        if time_diff <= best_time_diff:
            selected_time = pick_time
            best_time_diff = time_diff
            print("best picked time", pick_time, "is closest to", it_time)
       
    new_lon, new_lat = wrappedLinearInterpolation(params, day, selected_time)
    
   
    area = getTgtArea(rgb, new_lon, new_lat, radius)
    neighborRGB(area)
    
    filename = folder + str(radius) + '_modis_satellite_' + str(day) + '.npy'
    
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
    #post_processing(it, d, '20121022')
