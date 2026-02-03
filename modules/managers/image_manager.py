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
        
        # Yeni ekledik: model adına göre resim listelerini tutacak sözlük
        self.model_images_map = {}

    def load_images(self):
        """
        'images_folder' içindeki tüm alt klasörleri (os.walk) tarayarak,
        .png / .jpg / .jpeg dosyalarını bulur.

        - self.image_files : Tüm resimlerin 'altKlasor/dosya.png' formatında göreli yolu
        - self.model_images_map : "fabia" -> ["fabia1.jpg", "fabia2.png", ...] şeklinde bir sözlük

        Not: 'images_folder' yapınızı aşağıdaki gibi varsayıyoruz:
           images_folder/
               fabia/
                   fabia1.jpg
                   fabia2.jpg
               scala/
                   scala1.png
                   ...
               ...
        """
        if not os.path.exists(self.images_folder):
            raise FileNotFoundError(f"'{self.images_folder}' klasörü bulunamadı.")

        valid_extensions = ('.png', '.jpg', '.jpeg')
        self.image_files = []  # Sıfırlayalım
        self.model_images_map = {}  # Sözlüğü de sıfırlayalım

        for root, dirs, files in os.walk(self.images_folder):
            for file in files:
                if file.lower().endswith(valid_extensions):
                    full_path = os.path.join(root, file)
                    # 'images_folder' baz alınarak göreli yol
                    rel_path = os.path.relpath(full_path, start=self.images_folder)
                    # Windows'ta backslash yerine slash
                    rel_path = rel_path.replace("\\", "/")
                    
                    # Örneğin "fabia/dosya1.jpg" veya "scala/color/dosya2.png" gibi
                    self.image_files.append(rel_path)

                    # rel_path'i parçalayarak ilk klasör ismini (model adını) bulalım
                    # Örneğin "fabia/dosya1.jpg" -> model_name = "fabia", filename = "dosya1.jpg"
                    splitted = rel_path.split("/")
                    if len(splitted) >= 2:
                        model_name = splitted[0].lower().strip()  # fabia, scala vs.
                        filename = splitted[-1]  # "dosya1.jpg" (alt klasörler varsa splitted[1:-1])
                        
                        if model_name not in self.model_images_map:
                            self.model_images_map[model_name] = []
                        self.model_images_map[model_name].append(filename)
                    else:
                        # Eğer tek parçaysa, belki doğrudan model klasörü yoktur
                        # Ama chatbot kodu model bazlı aradığı için alt klasör mantığı gereklidir
                        pass

    def filter_images_multi_keywords(self, keywords_string: str):
        """
        'keywords_string'i kelimelere bölüp,
        her kelimenin resim yolunda (lowercase) geçip geçmediğine bakar.
        
        Bu metod, self.image_files içerisindeki tüm öğeleri tarar.
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

    # Yeni ekledik: Chatbot'un kullandığı metod
    def get_images_for_model(self, model_name: str):
        """
        Chatbot'ta self.image_manager.get_images_for_model(model) 
        çağrısını karşılamak için basit bir metod.
        
        'self.model_images_map' sözlüğünden model_name'e 
        ait olan resimlerin (sadece dosya adları) listesini döndürür.
        """
        model_name = model_name.lower().strip()
        return self.model_images_map.get(model_name, [])
