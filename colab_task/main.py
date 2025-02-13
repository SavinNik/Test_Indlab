import os
import requests
from bs4 import BeautifulSoup
import csv
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import openai
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки OpenAI API
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY

def get_first_parse(url_for_parse):
    """Функция для первого этапа парсинга (использует requests и BeautifulSoup)"""
    try:
        response = requests.get(url_for_parse)
        response.raise_for_status()  # Проверка статуса ответа
        html_content = response.content
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении данных с {url_for_parse}: {e}")
        return

    soup = BeautifulSoup(html_content, 'html.parser')
    artopp_elements = soup.find_all('div', class_='artopp')

    headers = ['Data-d', 'Data-a', 'Heading', 'Alert', 'Title', 'Date Updated', 'Body', 'URL']

    local_file_path = 'parse_files/artist_opportunities_12.csv'

    with open(local_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(headers)

        for artopp_element in artopp_elements:
            data_d = artopp_element.get('data-d', '')
            data_a = artopp_element.get('data-a', '')
            h3_text = artopp_element.find('h3', class_='b_categorical-heading mod--artopps').text.strip() if artopp_element.find('h3', class_='b_categorical-heading mod--artopps') else ''
            p_alert_text = artopp_element.find('p', class_='b_ending-alert mod--just-opened').text.strip() if artopp_element.find('p', class_='b_ending-alert mod--just-opened') else ''
            h2_text = artopp_element.find('h2').text.strip() if artopp_element.find('h2') else ''
            p_date_text = artopp_element.find('p', class_='b_date').text.strip() if artopp_element.find('p', class_='b_date') else ''
            main_body_text = artopp_element.find('div', class_='m_body-copy').text.strip() if artopp_element.find('div', class_='m_body-copy') else ''
            url_element = artopp_element.find('a', class_='b_submit mod--next')
            url = url_element.get('href') if url_element else ''

            row = [data_d, data_a, h3_text, p_alert_text, h2_text, p_date_text, main_body_text, url]
            csvwriter.writerow(row)

    print(f"Файл сохранен по пути: {local_file_path}")
    return local_file_path


def get_full_text(file_path):
    """Функция для второго этапа парсинга (использует Selenium для получения полного текста)"""
    # Настройка опций для Selenium
    chrome_options = Options()
    # chrome_options.add_argument('--headless=new')
    # chrome_options.add_argument('--no-sandbox')
    # chrome_options.add_argument('--disable-dev-shm-usage')
    # chrome_options.add_argument('--remote-debugging-port=9222')
    # chrome_options.add_argument('--user-data-dir=/tmp/user-data')
    # chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument("--disable-extensions")

    # Чтение существующего CSV файла
    df = pd.read_csv(file_path)

    # Добавление нового столбца для полного текста
    if 'Full Text' not in df.columns:
        df['Full Text'] = ""

    # Настройка Selenium WebDriver
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Ошибка при запуске ChromeDriver: {str(e)}")
        return

    # Проход по каждой ссылке в CSV и извлечение полного текста
    for index, row in df.iterrows():
        url = row['URL']
        if pd.notna(url) and url and pd.isna(row['Full Text']):
            try:
                print(f"Обработка URL: {url}")
                driver.get(url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                full_text = driver.find_element(By.TAG_NAME, "body").text.strip()
                df.at[index, 'Full Text'] = full_text
                print(f"Текст успешно извлечен для URL: {url}")
            except Exception as e:
                print(f"Ошибка при обработке URL {url}: {str(e)}")
                df.at[index, 'Full Text'] = "Could not load content"

    # Закрываем браузер
    driver.quit()

    # Сохранение обновленного CSV файла
    df.to_csv(file_path, index=False)
    print(f"Файл обновлен и сохранен по пути: {file_path}")

def ask_openai(question, prompt_prefix=""):
    """Задает вопрос OpenAI и возвращает ответ."""
    prompt = f"{prompt_prefix}\n\nQuestion: {question}\nAnswer:"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка при обращении к OpenAI: {e}")
        return "Error"


def process_csv_files(directory_path):
    """Обрабатывает все CSV файлы в папке, задает вопросы OpenAI и возвращает результаты."""
    results = []
    for file_name in os.listdir(directory_path):
        if file_name.endswith('.csv'):
            file_path = os.path.join(directory_path, file_name)
            try:
                df = pd.read_csv(file_path)
                print(f"Файл {file_path} успешно загружен.")
            except Exception as e:
                print(f"Ошибка при загрузке файла {file_path}: {e}")
                continue

            for _, row in df.iterrows():
                # Объединяем данные из строки с заголовками
                data = " ".join([f"{col}: {str(value)}" for col, value in row.items()])

                # Задаем вопросы OpenAI
                city_country = ask_openai(
                    f"Верни на английском языке ТОЛЬКО страну, если указано. Use UK for United Kingdom and USA for United States and full name for other countries. Данные: {data}. Если информации нет, то напиши Go to the application page for details.")
                print(city_country)
                opencall_title = ask_openai(
                    f"Верни на английском языке ТОЛЬКО название опен-колла. Оно может содержать название галереи, выставки, ярмарки и т.д. Данные: {data}. Если информации нет, то напиши Go to the application page for details.")
                print(opencall_title)
                deadline_date = ask_openai(
                    f"Верни на английском языке ТОЛЬКО дату дедлайна в формате YYYY-MM-DD. Данные: {data}. Если информации нет, то напиши 2024-10-30.")
                print(deadline_date)
                event_date = ask_openai(
                    f"Верни на английском языке ТОЛЬКО дату самого мероприятия (не дату дедлайна) в формате YYYY-MM-DD. Мероприятие всегда позже, чем дата дедлайна. Данные: {data}. Если информации нет, то напиши 2024-10-30.")
                print(event_date)
                application_form_link = ask_openai(
                    f"Верни на английском языке ТОЛЬКО ссылку на форму для подачи заявки. Обычно она находится в графе Website, Application Link, URL. Данные: {data}. Если информации нет, то напиши Go to the application page for details.")
                print(application_form_link)
                selection_criteria = ask_openai(
                    f"Верни на английском языке ТОЛЬКО критерии отбора художников и работ. Данные: {data}. Если информации нет, то напиши Go to the application page for details.")
                print(selection_criteria)
                fee = ask_openai(
                    f"Верни на английском языке ТОЛЬКО стоимость участия (не награду, а стоимость участия).Identify the participation fee based on the following information. Return only fee and nothing more. If there is 'no' or 'no fee' return 'no fee'. Without your thoughts. Данные: {data}. Если информации нет, то напиши Go to the application page for details.")
                print(fee)

                faq = ask_openai(
                    f"Составь на английском языке ТОЛЬКО FAQ по следующему формату (ЭТО ПРИМЕРНЫЙ ФОРМАТ, ТЫ МОЖЕШЬ ДОБАВЛЯТЬ ИЛИ УБИРАТЬ ПУНКТЫ): \n"
                    "Who is eligible for this opportunity?: \n"
                    "When is the deadline?: \n"
                    "How many works can I submit?: \n"
                    "When is the delivery date?: \n"
                    "When do I need to collect my work?: \n"
                    "How much does it cost?: \n"
                    "Are there payments to artists?: \n"
                    "How do you decide on proposals?: \n"
                    "What happens if my proposal is chosen?:\n"
                    "What kind of proposals are you looking for?: \n"
                    "Where is the [OPPORTUNITY NAME] held?: \n"
                    "Why we do it: \n"
                    f"Данные: {data}. Если информации нет, то напиши Go to the application page for details."
                )
                print(faq)

                application_guide = ask_openai(
                    f"Верни на английском языке ТОЛЬКО подробный и написанный простыми словами план для художника, как податься на опен-колл. Без воды и банальностей, а только полезная инфа, основанная на данных опен-колла и основные шаги из общей практики подачи заявок на опен-колл. Так чтобы художник смог скопировать и вставить в свой список дел. Также ты можешь использовать свои знания о площадке проведения опен-колла для уточнения плана. Данные: {data}. Если информации нет, то напиши Go to the application page for details.")
                print(application_guide)

                # Сохраняем результаты
                results.append({
                    "City_Country": city_country,
                    "Open_Call_Title": opencall_title,
                    "Deadline_Date": deadline_date,
                    "Event_Date": event_date,
                    "Application_Form_Link": application_form_link,
                    "Selection_Criteria": selection_criteria,
                    "FAQ": faq,
                    "Application_Guide": application_guide,
                    "Fee": fee
                })
    return results

def save_results(results, output_file):
    """Сохраняет результаты в CSV файл с удалением дубликатов."""
    try:
        # Преобразуем результаты в DataFrame
        df_results = pd.DataFrame(results)

        # Удаляем дубликаты на основе столбцов "Open_Call_Title" и "Application_Form_Link"
        df_results.drop_duplicates(subset=["Open_Call_Title", "Application_Form_Link"], keep="first", inplace=True)

        # Сохраняем очищенные данные в файл
        df_results.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"Результаты успешно сохранены в {output_file}. Дубликаты удалены.")
    except Exception as e:
        print(f"Ошибка при сохранении файла: {e}")

def send_post_request(row):
    """Отправка POST-запросов"""
    url = "https://beta.mirr.art/api/open_calls/"
    headers = {
        "Authorization": "Bearer ed1beebf3ede45c9a55835b5166c10b5",
        "Accept": "application/json"
    }
    data = {
        "city_country": row['City_Country'],
        "open_call_title": row['Open_Call_Title'],
        "deadline_date": row['Deadline_Date'],
        "event_date": row['Event_Date'],
        "application_from_link": row['Application_Form_Link'],
        "selection_criteria": row['Selection_Criteria'],
        "faq": row['FAQ'],
        "fee": row['Fee'],
        "application_guide": row['Application_Guide'],
        "open_call_description": f"Open call in {row['City_Country']} titled {row['Open_Call_Title']}."
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"Успешно отправлены данные для Open Call: {row['Open_Call_Title']}")
        else:
            print(f"Ошибка при отправке данных для Open Call: {row['Open_Call_Title']}. Статус код: {response.status_code}")
    except Exception as e:
        print(f"Ошибка при отправке POST-запроса: {e}")

def process_csv_and_send_requests(file_path):
    """Чтение CSV и отправка данных"""
    try:
        df = pd.read_csv(file_path, encoding='ISO-8859-1')
        print(f"Файл {file_path} успешно загружен.")
    except Exception as e:
        print(f"Ошибка при загрузке файла {file_path}: {e}")
        return

    required_fields = ['City_Country', 'Open_Call_Title', 'Deadline_Date', 'Event_Date', 'Application_Form_Link']
    for _, row in df.iterrows():
        if not all(field in row for field in required_fields):
            print(f"Пропущены обязательные поля в записи: {row.get('Open_Call_Title', 'Неизвестно')}")
            continue
        send_post_request(row)

# Основная функция
def main():
    # Шаг 1: Парсим данные
    url_for_parse = "https://www.artrabbit.com/artist-opportunities/"
    file_path = get_first_parse(url_for_parse)

    if file_path:
        # Шаг 2: Получаем полный текст
        get_full_text(file_path)

        # Шаг 3: Обрабатываем данные через OpenAI
        results = process_csv_files(os.path.dirname(file_path))
        output_file = "processed_opencalls.csv"
        save_results(results, output_file)

        # Шаг 4: Отправляем данные на сервер
        process_csv_and_send_requests(output_file)


if __name__ == "__main__":
    main()