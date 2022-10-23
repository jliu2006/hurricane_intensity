from modis_tools.auth import ModisSession
from modis_tools.resources import CollectionApi, GranuleApi
from modis_tools.granule_handler import GranuleHandler

username = "lxg0601"  # Update this line
password = "Xian2021"  # Update this line







def download_file(folder, start_date, end_date):

    # Authenticate a session
    session = ModisSession(username=username, password=password)

    # Query the MODIS catalog for collections
    collection_client = CollectionApi(session=session)

    collections = collection_client.query(short_name="MOD09CMG", version="006")

    # Query the selected collection for granules
    granule_client = GranuleApi.from_collection(collections[0], session=session)

    # Filter the selected granules via spatial and temporal parameters
    nigeria_bbox = [-76, 14, -60, 20]
    nigeria_granules = granule_client.query(start_date="2012-10-24", end_date="2012-10-25", bounding_box=nigeria_bbox)

    # Download the granules
    GranuleHandler.download_from_granules(nigeria_granules, session)


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
        download_file(folder, "2012-10-24",  "2012-10-25")
    
        
hurricanes_folders = glob("/home/fun/data/*201201/", recursive = True)

for it in hurricanes_folders:
    download_modis(it)
