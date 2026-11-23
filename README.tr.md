# ubl-invoice-audit

[![CI](https://github.com/Rovtal/ubl-invoice-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/Rovtal/ubl-invoice-audit/actions/workflows/ci.yml)

Dil: [English](README.md) | **Türkçe**

%100 çevrimdışı çalışan, **KVKK uyumlu** UBL-TR (e-Fatura / e-Arşiv) XML ve iç içe ZIP ayrıştırıcı, matematiksel KDV/matrah/tevkifat/mükerrer denetçisi ve çok sayfalı Excel (`.xlsx`) raporlayıcı.

## Neden Çevrimdışı?

GİB ve özel entegratörlerden indirilen `.zip` ve `.xml` faturaları 3. parti web sitelerine yüklemeden veya belge başına kontör ödemeden doğrudan yerel bilgisayarda denetler:

- **İç İçe ZIP, XXE ve CWE-1236 Koruması:** GİB arşivlerindeki iç içe `.zip` paketlerini bellekte açar; dış varlık (`XXE`) çözümleme, yol geçişi (`zip-slip`), açılma boyutu sınırları ve Excel formül enjeksiyonu (`CWE-1236`) korumalıdır.
- **Kesin `Decimal` Matematik Denetimi:** Kayan nokta (`float`) yuvarlama hatası olmadan kalem toplamı, iskonto/artırım, çoklu KDV oranları, `TaxTotal`, `WithholdingTaxTotal` (tevkifat), `TaxInclusiveAmount` ve `PayableAmount` mutabakatını doğrular.
- **Mükerrer ve Çift Kayıt Yakalama:** Aynı `ETTN (UUID)`, aynı satıcıda tekrar eden Fatura No ve aynı satıcı + tarih + tutarlı olası çift kayıtları ayırır.
- **Şahıs Firması ve Çoklu Oran Desteği:** Hem `PartyName` (`VKN`) hem `Person` (`TCKN`) yapısını okur.
- **5 Sayfalı Biçimli Excel Çıktısı:** `Ozet_Denetim` (yerel `COUNTIF`/`SUM` formülleri + KDV kırılımı), `Faturalar`, `Kalem_Detay`, `KDV_Kirilim`, `Uyari_ve_Mukerrer`.

## Kurulum ve Kullanım

Python 3.10+ gerektirir (`XlsxWriter`, `lxml`).

```powershell
cd ubl-invoice-audit
pip install -e .[dev]
```

### 1. Hazır Demo (Örnek Faturalar + Rapor)

```powershell
ubl-audit demo --out-dir demo_output
```

### 2. Gerçek Klasör / XML / ZIP Denetimi

Hata bulunduğunda çıkış kodu `2` döndürmesi için `--fail-on-error`, satıcı `VKN`/`TCKN` kontrol basamağı doğrulaması için `--verify-tax-id`, İngilizce çıktı için `--lang en` ekleyin:

```powershell
ubl-audit audit .\faturalar_klasoru .\arsiv.zip -o .\rapor.xlsx --json .\ozet.json --verify-tax-id --fail-on-error
```

## Test

```powershell
python -m unittest discover -s tests -v
```

(`pytest` kurulu ortamlarda `pytest -v` de doğrudan çalışır.)

## Lisans

[MIT](LICENSE) — Rovtal
