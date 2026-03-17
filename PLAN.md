Currently we use BeautifulSoup to parse some HTML.
It turns out that it is unnecessary because Mirrorcache provides JSON output too.
Fetch and compare:
- https://download.opensuse.org/repositories/systemsmanagement:/Agama:/Devel/images/iso/?jsontable
- https://download.opensuse.org/repositories/systemsmanagement:/Agama:/Devel/images/iso/

Remove the BeautifulSoup dependency in favor of using the jsontable data.
