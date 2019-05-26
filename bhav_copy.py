import cherrypy
from jinja2 import FileSystemLoader, Environment
from bs4 import BeautifulSoup as Soup
from requests import get
import re
import io
import zipfile
import redis
import csv


env = Environment(loader=FileSystemLoader('templates'))


class BhavCopy:
    def __init__(self):
        self.hostname = '127.0.0.1'
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
                    line_count += 1
                    pipe.hmset(scrip_details['Scrip Name'], scrip_details)
            redis_query_result = pipe.execute()

        # return True if all redis operations executed successfully
        if False not in redis_query_result:
            return True
        else:
            return False

    def get_top_entries_redis(self):
        result = list()
        scrip_details = dict()
        count = 0
        for i in self.r.scan_iter():
            if count >= 10:
                break
            count += 1
            data = (self.r.hgetall(i))
            data = {key.decode('utf-8'): value.decode('utf-8') for key, value in data.items()}
            print(data)
            result.append(data)
        return result

    @cherrypy.expose
    def get_bhav_copy(self):
        bhav_copy_url = "https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx"
        template = env.get_template('display.html')

        # get response object from url
        response = get(bhav_copy_url)
        soup = Soup(response.content, 'html.parser')

        # find all links with text Equity
        links = soup.findAll('a', text=re.compile('Equity'), href=True)

        # first link belongs to latest Bhav Copy Zip
        zip_file_url = links[0]['href']

        # get zip content
        zip_file_request = get(zip_file_url)
        z = zipfile.ZipFile(io.BytesIO(zip_file_request.content))

        # Extract in CWD
        z.extractall('.')

        # assuming zip contains only one file
        file_name = z.namelist()[0]
        result = self.dump_to_redis(file_name)
        if result is True:
            top_entries = self.get_top_entries_redis()
            return template.render(text="CSV dumped into Redis", top_entries=top_entries)
        return template.render(text="Error while dumping into redis")

    @cherrypy.expose
    def get_scrip_details(self, scrip_name=None):
        template = env.get_template('result.html')
        if self.r.hexists(scrip_name, "Scrip Name"):
            data = self.r.hgetall(scrip_name)
            data = {key.decode('utf-8'): value.decode('utf-8') for key, value in data.items()}
            return template.render(result=data)
        else:
            return template.render(result="Not avaliable")


if __name__ == "__main__":
    cherrypy.config.update({'server.socket_port': 8082})
    cherrypy.quickstart(BhavCopy())
