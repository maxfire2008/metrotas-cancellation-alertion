from pprint import pprint
import requests
import bs4
import datetime
import re
import DatabaseController


database_controller = DatabaseController.DatabaseController("sqlite:///database.db")


def includes(a, b):
    if a is None:
        return True
    return a.lower() in b.lower()


def process_article(date, title, url, description, location):
    print(f"{date} - {title} - {url} - {description} - {location}")
    if "Service Update" not in title:
        return

    article_content = requests.get(url, timeout=60)
    soup = bs4.BeautifulSoup(article_content.content, "html.parser")
    article = soup.find("article")

    for paragraph in article.findAll("p"):
        # replace \xa0+  with " "
        text = re.sub(r" +", " ", paragraph.text.replace("\xa0", " "))

        for alert in database_controller.get_alerts():
            if (
                includes(alert.route, text)
                and includes(alert.direction, text)
                and includes(alert.time, text)
            ):
                print("SENDING NOTIFICATION FOR", alert)
                database_controller.send_notification(
                    alert.user_id, text, hash=repr((url, text))
                )


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

        process_article(date, title, url, description, location)


if __name__ == "__main__":
    main()
