from pprint import pprint
import requests
import bs4
import datetime


def main():
    alerts_index = requests.get("https://www.metrotas.com.au/alerts/", timeout=10)
    soup = bs4.BeautifulSoup(alerts_index.content, "html.parser")
    articles = soup.find("div", {"class": "article-body col-md-9"})
    for article in articles.findAll("article"):
        date = datetime.datetime.fromisoformat(article.find("time").attrs["datetime"])
        title = article.find("h4").text
        url = article.find("a").attrs["href"]
        description = article.find("p").text
        if description == "":
            description = None
        location = article.find("span").text

        print(f"{date} - {title} - {url} - {description} - {location}")


if __name__ == "__main__":
    main()
