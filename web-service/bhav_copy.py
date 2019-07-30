import cherrypy
import os
from jinja2 import FileSystemLoader, Environment
from bs4 import BeautifulSoup as Soup
import requests
import re
import io
import zipfile
import redis
import csv
import json
import logging

env = Environment(loader=FileSystemLoader('templates'))
logging.basicConfig(filename='bhav_copy.log', level=logging.DEBUG, 
                    format='%(asctime)s:%(levelname)s:%(message)s')

class BhavCopy:
    def __init__(self):
        # hostname for deployment in a single task
        self.hostname = 'localhost'
        # hostname for docker compose up
        # self.hostname = 'redis'
        self.port = '6379'
        self.r = redis.Redis(host=self.hostname, port=self.port)
        logging.debug("Current redis hostname : {} and port : {}".format(self.hostname, self.port))
        logging.debug("Redis Hostname for AWS task should be 'localhost' and for local deployment it should be 'redis'")

    @cherrypy.expose
    def index(self):
        template = env.get_template('index.html')
        return template.render()

    def dump_to_redis(self, file_name):
        logging.debug('Inside dump_to_redis function')
        logging.debug('Opening downloaded bhavcopy csv ...')
        with open(file_name) as bhav_copy_csv:
            csv_reader = csv.reader(bhav_copy_csv, delimiter=',')
            line_count = 0
            scrip_details = dict()
            pipe = self.r.pipeline()
            for row in csv_reader:
                logging.debug('Skip row containing columns name')
                # Skip first row having column names
                if line_count == 0:
                    line_count += 1
                else:
                    # Remove trailing spaces with rstrip()
                    scrip_details['Scrip Code'] = str(row[0]).rstrip()
                    scrip_details['Scrip Name'] = str(row[1]).rstrip()
                    scrip_details['Open'] = str(row[4]).rstrip()
                    scrip_details['High'] = str(row[5]).rstrip()
                    scrip_details['Low'] = str(row[6]).rstrip()
                    scrip_details['Close'] = str(row[7]).rstrip()
                    # print(scrip_details)
                    pipe.hmset(scrip_details['Scrip Name'], scrip_details)
            redis_query_result = pipe.execute()

        # return True if all redis operations executed successfully
        if False not in redis_query_result:
            logging.debug('Entires dumped to redis successfully.')
            return True
        else:
            logging.debug('Failed to dump entries to redis.')
            return False

    def get_top_entries_redis(self):
        logging.debug('Getting 10 entries from redis.')
        result = []
        # scrip_details = dict()
        count = 0
        for i in self.r.scan_iter():
            if count >= 10:
                break
            count += 1
            data = (self.r.hgetall(i))
            data = {key.decode('utf-8'): value.decode('utf-8') for key, value in data.items()}
            # print(data)
            result.append(data)
        return result

    @cherrypy.expose
    def get_bhav_copy(self):

        bhav_copy_url = "https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx"

        try:
            # get response object from url
            response = requests.get(bhav_copy_url)
            logging.debug('Url {} reachable and get request is successful'.format(bhav_copy_url))
        except requests.exceptions.Timeout as err_t:
            error = {}
            error["Error"] = "Error : " + str(err_t)
            logging.debug(error["Error"])
            return json.dumps([error])
        except requests.exceptions.HTTPError as err_h:
            error = {}
            error["Error"] = "Error : " + str(err_h)
            logging.debug(error["Error"])
            return json.dumps([error])
        except requests.exceptions.ConnectionError as err_c:
            error = {}
            error["Error"] = "Error : " + str(err_c)
            logging.debug(error["Error"])
            return json.dumps([error])
        except requests.exceptions.RequestException as err:
            error = {}
            error["Error"] = "Error : " + str(err)
            logging.debug(error["Error"])
            return json.dumps([error])
        else:
            soup = Soup(response.content, 'html.parser')

            # find all links with text Equity
            links = soup.findAll('a', text=re.compile('Equity'), href=True)

            # first link belongs to latest Bhav Copy Zip
            zip_file_url = links[0]['href']
            
            # latest bhav_copy available
            latest_bhavcopy_date = links[0].text
            logging.debug('Bhav Copy Date : {}'.format(latest_bhavcopy_date))

            # get zip content
            zip_file_request = requests.get(zip_file_url)
            z = zipfile.ZipFile(io.BytesIO(zip_file_request.content))

            # Extract in CWD
            z.extractall('.')

            # assuming zip contains only one file
            file_name = z.namelist()[0]
            result = self.dump_to_redis(file_name)
            if result is True:
                top_entries = self.get_top_entries_redis()
                logging.debug('First of 10 entries {}'.format(top_entries[0]))
                return json.dumps(top_entries)
            else:
                error = {}
                error["Error"] = "Error dumping entires into redis. " 
                return json.dumps([error])

    @cherrypy.expose
    def get_scrip_details(self, scrip_name):
        logging.debug('Search request for scrip : {}'.format(scrip_name))
        scrip_name = str(scrip_name)
        if self.r.hexists(scrip_name, "Scrip Name"):
            logging.debug('Scrip exists.')
            data = self.r.hgetall(scrip_name)
            data = {key.decode('utf-8'): value.decode('utf-8') for key, value in data.items()}
            logging.debug('Scrip details : {}',format(data))
            result = []
            result.append(data)
            return json.dumps(result)
        else:
            return json.dumps([])


if __name__ == "__main__":
    cherrypy.config.update({'server.socket_host': '0.0.0.0',
                        'server.socket_port': 80,
                       })
    conf = {
        '/': {
            'tools.sessions.on': True,
            'tools.staticdir.root': os.path.abspath(os.getcwd())
        },
        '/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': './templates'
        }
    }
    cherrypy.quickstart(BhavCopy(),'/', conf)
