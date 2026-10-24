# Sarıgüzel Teklif API

FastAPI tabanlı DXF analiz ve teklif oluşturma uygulaması.

## Çalıştırma

```powershell
pip install -r requirements.txt
uvicorn main:app --reload
```

Uygulama `http://127.0.0.1:8000` adresinde, API şeması ise
`http://127.0.0.1:8000/docs` adresinde açılır.

## API

| Method | Endpoint | Açıklama |
| --- | --- | --- |
| `POST` | `/api/dxf-analiz` | DXF dosyalarını analiz eder. Dosya başına 10 MB, istek başına 20 dosya sınırı vardır. |
| `GET` | `/api/ornek-10-parca` | Örnek parçaların analiz sonuçlarını döndürür. |
| `GET` | `/api/test-dxf-zip-indir` | Örnek DXF dosyalarını ZIP olarak indirir. |
| `POST` | `/api/kurumsal-pdf-indir` | Doğrulanmış teklif verilerinden PDF oluşturur. |

DXF analizinde çizgiler, daireler, yaylar, polylineler, elipsler, spline'lar ve
bloklar desteklenir. Ölçüler çizim koordinat birimi cinsinden değerlendirilir;
uygulama bunları milimetre olarak gösterdiğinden, DXF çiziminin milimetre
biriminde hazırlanmış olması beklenir. Analiz edilemeyen kesim geometrileri
başarılı sonuç gibi atlanmaz, açıklayıcı bir hata döndürülür.

## Proje yapısı

- `app/api/`: HTTP uç noktaları
- `app/core/`: uygulama yapılandırması
- `app/schemas/`: istek modelleri ve doğrulama kuralları
- `app/services/`: DXF analizi, örnek dosyalar ve PDF üretimi
- `app/templates/`: web arayüzü
- `main.py`: mevcut Uvicorn çalıştırma komutlarıyla uyumluluk giriş noktası
