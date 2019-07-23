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

env = Environment(loader=FileSystemLoader('templates'))


class BhavCopy:
    def __init__(self):
        self.hostname = 'redis'
        self.port = '6379'
        self.r = redis.Redis(host=self.hostname, port=self.port)

    @cherrypy.expose
    def index(self):
        template = env.get_template('index.html')
        return template.render()

    def dump_to_redis(self, file_name):
        with open(file_name) as bhav_copy_csv:
            csv_reader = csv.reader(bhav_copy_csv, delimiter=',')
            line_count = 0
            scrip_details = dict()
            pipe = self.r.pipeline()
            for row in csv_reader:
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
                    line_count += 1
                    pipe.hmset(scrip_details['Scrip Name'], scrip_details)
            redis_query_result = pipe.execute()

        # return True if all redis operations executed successfully
        if False not in redis_query_result:
            return True
        else:
            return False

    def get_top_entries_redis(self):
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
        except requests.exceptions.Timeout as err_t:
            template = env.get_template('error.html')
            return template.render(text="Timeout Error : "+ str(err_t))
        except requests.exceptions.HTTPError as err_h:
            template = env.get_template('error.html')
            return template.render(text="HTTPError Error : "+ str(err_h))
        except requests.exceptions.ConnectionError as err_c:
            template = env.get_template('error.html')
            return template.render(text="Error Connecting : "+ str(err_c))
        except requests.exceptions.RequestException as err:
            template = env.get_template('error.html')
            return template.render(text="Request Error : "+ str(err))
        else:
            template = env.get_template('display.html')
            soup = Soup(response.content, 'html.parser')

            # find all links with text Equity
            links = soup.findAll('a', text=re.compile('Equity'), href=True)

            # first link belongs to latest Bhav Copy Zip
            zip_file_url = links[0]['href']
            
            # latest bhav_copy available
            latest_bhavcopy_date = links[0].text
            print(latest_bhavcopy_date)

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
                print(len(top_entries))
                print(top_entries[0])
                # return template.render(flag=0, text="CSV dumped into Redis", top_entries=top_entries)
                print("--------------------------------------")
                print(top_entries)
                print("--------------------------------------")
                return json.dumps(top_entries)
            return template.render(flag=1, text="Error while dumping into redis")

    @cherrypy.expose
    # @cherrypy.tools.json_in()
    # @cherrypy.tools.json_out()
    def get_scrip_details(self, scrip_name):
        # json_obj = cherrypy.request.json
        # scrip_name = json_obj['scrip_name']
        # template = env.get_template('result.html')
        # if scrip_name is None:
        #     return template.render(result="No Scrip name provided")
        # a = cherrypy.requests.json
        # scrip_name = a['scrip_name']
        scrip_name = str(scrip_name)
        if self.r.hexists(scrip_name, "Scrip Name"):
            data = self.r.hgetall(scrip_name)
            data = {key.decode('utf-8'): value.decode('utf-8') for key, value in data.items()}
            result = []
            print(data)
            result.append(data)
            return json.dumps(result)
        else:
            return json.dumps([])
        # else:
            # return template.render(result="Not avaliable")


if __name__ == "__main__":
    cherrypy.config.update({'server.socket_host': '0.0.0.0',
                        'server.socket_port': 5000,
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
