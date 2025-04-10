import os
import re
from PIL import Image
import matplotlib.pyplot as plt
from modules.config import Config

class ImageManager:
    def __init__(self, images_folder=None):
        self.config = Config()
        self.images_folder = images_folder if images_folder else self.config.image_paths
        self.image_files = []
        self.stopwords = self.config.stopwords

    def load_images(self):
        """
        'images_folder' içindeki tüm alt klasörleri (os.walk) tarayarak,
        .png / .jpg / .jpeg dosyalarını bulur.
        'self.image_files' listesine her bir dosyanın, ana klasöre göre
        göreli yolunu 'altKlasor/dosya.png' formatında ekler.
        """
        if not os.path.exists(self.images_folder):
            raise FileNotFoundError(f"'{self.images_folder}' klasörü bulunamadı.")

        valid_extensions = ('.png', '.jpg', '.jpeg')
        self.image_files = []  # Önce temizleyelim

        for root, dirs, files in os.walk(self.images_folder):
            for file in files:
                if file.lower().endswith(valid_extensions):
                    full_path = os.path.join(root, file)
                    # 'images_folder' baz alınarak göreli yol
                    rel_path = os.path.relpath(full_path, start=self.images_folder)
                    # Windows'ta backslash yerine slash
                    rel_path = rel_path.replace("\\", "/")
                    self.image_files.append(rel_path)

    def filter_images_multi_keywords(self, keywords_string: str):
        """
        'keywords_string'i kelimelere bölüp,
        her kelimenin resim yolunda (lowercase) geçip geçmediğine bakar.
        """
        splitted_raw = keywords_string.lower().split()
        splitted = [word for word in splitted_raw if word not in self.stopwords]

        matched_files = []
        for img in self.image_files:
            img_lower = img.lower()
            # Tüm aranan kelimeler img_lower'da var mı?
            if all(word in img_lower for word in splitted):
                matched_files.append(img)
        return matched_files

    def display_images(self, image_list):
        """
        (Opsiyonel) Matplotlib ile görselleri anlık gösterir. 
        Sunucu tarafında çok kullanılmaz, ama debug amaçlı durabilir.
        """
        for image_name in image_list:
            image_path = os.path.join(self.images_folder, image_name)
            with Image.open(image_path) as img:
                plt.figure(figsize=(8, 6))
                plt.imshow(img)
                plt.axis("off")
                plt.title(os.path.splitext(image_name)[0])
                plt.show()
