from core.api import LibraryAPI



def test_get_chapter_pages():
    api = LibraryAPI()

    json_data = api.get_chapter_pages_json(109)

    print("JSON Data:", json_data)

if __name__ == "__main__":
    test_get_chapter_pages()