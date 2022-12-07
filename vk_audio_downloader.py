import os
import random
import sys
import time
from typing import List, Tuple

import m3u8
import pandas as pd
import requests
import vk_api
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from vk_api import audio

REQUEST_STATUS_CODE = 200
DEFAULT_SAVE_DIR = "music/"
TEMP_AUDIO_FILE_NAME = "temp.ts"
DEFAULT_PATH_TO_HISTORY="history.txt"


def two_factor():
    code = input('Code? ')
    return code, True


class MusicDownloader:
    def __init__(self, login: str, password: str, save_dir: str = None):
        self._vk_session = vk_api.VkApi(
            login=login,
            password=password, 
            auth_handler=two_factor,
        )
        self._vk_session.auth()
        print("вошел в {}".format(login), file=sys.stderr)
        self._vk_audio = audio.VkAudio(self._vk_session)
        self.save_dir = save_dir or DEFAULT_SAVE_DIR
        self.temp_file_path = f"{self.save_dir}/{TEMP_AUDIO_FILE_NAME}"

    def download_audio_by_id(self, owner_id: int, audio_id: int, convert_to_mp3: bool = False, verbose: bool = False):
        """Скачивает аудио по id трека

        Params
        ------
        owner_id: ID владельца (отрицательные значения для групп)
        audio_id: ID аудио
        verbose: Вывод времени выполнения
        """
        if verbose:
            start = time.time()

        os.makedirs(self.save_dir, exist_ok=True)

        m3u8_data, m3u8_url, meta_info = self._get_m3u8_by_id(owner_id, audio_id)
        parsed_m3u8 = self._parse_m3u8(m3u8_data)
        segments_binary_data = self._get_audio_from_m3u8(parsed_m3u8=parsed_m3u8, m3u8_url=m3u8_url)

        audio_name = f"{owner_id}_{audio_id}"
        if convert_to_mp3:
            self._write_to_mp3(segments_binary_data, name=audio_name)
        else:
            audio_path = f"{self.save_dir}/{audio_name}.ts"
            self._write_to_file(segments_binary_data, path=audio_path)

        if verbose:
            print(f"{audio_name} saved in {time.time() - start:.2f} sec")

    def _get_m3u8_by_id(self, owner_id: int, audio_id: int) -> Tuple:
        """
        Params
        ------
        owner_id: ID владельца (отрицательные значения для групп)
        audio_id: ID аудио

        Returns
        -------
        data: сожержимое m3u8 файла
        url: сылка на m3u8 файл
        meta_info: Dict['artist': str, 'title': str]
        """
        audio_info = self._vk_audio.get_audio_by_id(owner_id=owner_id, audio_id=audio_id)
        url = audio_info.get("url")
        data = m3u8.load(uri=url)
        meta_info = {
            "artist": audio_info.get("artist"),
            "title": audio_info.get("title"),
            "duration": audio_info.get("duration"),
        }
        return data, url, meta_info

    @staticmethod
    def _parse_m3u8(m3u8_data):
        """Возвращает информацию о сегментах"""
        parsed_data = []
        segments = m3u8_data.data.get("segments")
        for segment in segments:
            temp = {"name": segment.get("uri")}

            if segment["key"]["method"] == "AES-128":
                temp["key_uri"] = segment["key"]["uri"]
            else:
                temp["key_uri"] = None

            parsed_data.append(temp)
        return parsed_data

    @staticmethod
    def _download_content(url: str) -> bytes:
        response = requests.get(url=url)
        return response.content if response.status_code == REQUEST_STATUS_CODE else None

    @staticmethod
    def _encode_aes_128(data: bytes, key: bytes) -> bytes:
        """Декодирование из AES-128 по ключу"""
        iv = data[0:16]
        ciphered_data = data[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        encoded = unpad(cipher.decrypt(ciphered_data), AES.block_size)
        return encoded

    def _get_audio_from_m3u8(self, parsed_m3u8: List, m3u8_url: str) -> bytes:
        """Скачивает сегменты и собирает их в одну байт-строку"""
        downloaded_segments = []
        for segment in parsed_m3u8:
            segment_uri = m3u8_url.replace("index.m3u8", segment["name"])
            audio_content = self._download_content(segment_uri)

            if segment["key_uri"] is None:
                downloaded_segments.append(audio_content)
            else:
                key = self._download_content(url=segment["key_uri"])
                downloaded_segments.append(
                    self._encode_aes_128(data=audio_content, key=key)
                )
        return b''.join(downloaded_segments)

    @staticmethod
    def _write_to_file(data: bytes, path: str):
        with open(path, "wb+") as f:
            f.write(data)

    def _write_to_mp3(self, segments_binary_data: bytes, name: str):
        """Записывает бинарные данные в файл и конвертирует его в .mp3"""
        mp3_path = f"{self.save_dir}/{name}.mp3"

        self._write_to_file(data=segments_binary_data, path=self.temp_file_path)

        if not os.path.isfile(mp3_path):
            os.system(f'ffmpeg -hide_banner -loglevel error -i {self.temp_file_path} -vn -acodec copy -y {mp3_path}')
            os.remove(f"{self.temp_file_path}")
        else:
            os.remove(f"{self.temp_file_path}")
            raise Exception(f"Файл {mp3_path} уже существует, задайте другое имя.")

    def search(self, q: str, count: int):
        """Поиск треков по запросу

        Params
        ------
        q:
            Запрос
        count:
            Количество треков в выдаче

        Returns
        -------
        Список словарей с мета-информацией о треках
        """
        response = self._vk_audio.search(q=q, count=count)
        return list(response)

    def download_by_m3u8_url(self, m3u8_url):
        """Загрузка и сохранение аудио по m3u8 ссылке"""
        m3u8_data = m3u8.load(uri=m3u8_url)
        parsed_m3u8 = self._parse_m3u8(m3u8_data)
        segments_binary_data = self._get_audio_from_m3u8(parsed_m3u8=parsed_m3u8, m3u8_url=m3u8_url)

        os.makedirs(self.save_dir, exist_ok=True)
        audio_name = f"temp"
        audio_path = f"{self.save_dir}/{audio_name}.ts"
        self._write_to_file(segments_binary_data, path=audio_path)


def main():
    try:
        path_to_tracks = sys.argv[1]
    except:
        print("ERROR\nUSAGE: python3 {} PATH_TO_TRACKS.csv [PATH_TO_HISTORY.txt]".format(os.path.basename(sys.argv[0])), file=sys.stderr)
        exit(1)

    path_to_history = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_PATH_TO_HISTORY

    if os.path.exists(path_to_tracks):
        df = pd.read_csv(path_to_tracks)
        print("df.shape =", df.shape)
    else:
        raise("Path '{}' doesn't exist".format(path_to_tracks))
    
    history = set()
    if os.path.exists(path_to_history):
        with open(path_to_history) as fin:
            for line in fin:
                history.add(line.strip())
        df = df[~df.vk_id.isin(history)]
        print("df.shape after filtration =", df.shape)
    else:
        print("history is empty", file=sys.stderr)

    history_file = open(path_to_history, "a")

    login = os.environ.get("VK_LOGIN")
    password = os.environ.get("VK_PASSWORD")

    downloader = MusicDownloader(login=login, password=password)

    # owner_id = 371745470
    # audio_id = 456463164
    # downloader.download_audio_by_id(owner_id=owner_id, audio_id=audio_id, verbose=True, convert_to_mp3=True)
    ntries = 0
    for i, vk_id in enumerate(df.vk_id.values):
        print("{}. Processing '{}'".format(i, vk_id))
        owner_id, audio_id = map(int, vk_id.split("_"))
        try:
            downloader.download_audio_by_id(owner_id=owner_id, audio_id=audio_id, verbose=True, convert_to_mp3=False)
            ntries = 0
        except StopIteration as e:
            print("ERROR {}".format(repr(e)))
        except Exception as e:
            ntries += 1
            print("-------------------\nERROR")
            print(repr(e))
            print(e.__doc__)
            print("-------------------")

        history_file.write(vk_id + "\n")

        if ntries == 10:
            break

        time.sleep(random.randint(2, 6))
        if i % 20 == 0:
            time.sleep(random.randint(8, 13))

    history_file.close()


if __name__ == "__main__":
    for _ in range(10):
        main()
        time.sleep(random.randint(60, 120))
