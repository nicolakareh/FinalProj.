# Flag Pharmacy — website

A minimal, modern, dependency-free redesign of [flagpharmacy.com](https://www.flagpharmacy.com/), the full-service pharmacy at 7 Willow Street in Lynn, MA and Margolis Pharmacy at 447 Broadway in Chelsea, MA. Seventeen pages, one stylesheet, one script, no build tools required to view it.

## Pages

| File | Original page |
| --- | --- |
| `index.html` | Home |
| `about.html` | About |
| `patients.html` | Patients (hub) |
| `new-prescriptions.html` | New Prescriptions |
| `refills.html` | Refills · Transfer Prescriptions |
| `mobile-apps.html` | Mobile Apps |
| `ask-the-pharmacist.html` | Ask the Pharmacist |
| `home-delivery.html` | Home Delivery |
| `adherence-program.html` | Adherence Program |
| `synchronize-medication-program.html` | Synchronize Medication Program |
| `unit-dose.html` | Unit Dose |
| `medication-therapy-management.html` | Medication Therapy Management |
| `vaccines.html` | All Vaccine Appointments |
| `health-care-providers.html` | Health Care Providers |
| `store.html` | Store / Products |
| `locations.html` | Locations |
| `margolis-pharmacy.html` | Margolis Pharmacy |

## Run it locally

Open `index.html` in a browser, or serve the folder:

```bash
cd flag-pharmacy
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Photos

The original site's photographs could not be downloaded automatically. Every
place a photo belongs is a labeled slot; see `assets/img/README.md` for the
list of filenames to drop in. Once the files are present they appear with no
code changes.

## Editing

The root HTML files are **generated** from `src/`:

```
src/
  build.js      # assembles pages → flag-pharmacy/   (node flag-pharmacy/src/build.js)
  partials/     # head, header (nav), footer
  pages/        # one file per page; the <!--META …--> comment sets title, description, slug, nav group
```

Two shorthands are expanded at build time: `{{ICON name}}` for an inline SVG icon and
`{{PHOTO file.jpg|Caption|Alt text|optional-class}}` for a photo slot.

Styles live in `assets/css/site.css` (design tokens at the top), behavior in `assets/js/site.js`:
mobile navigation, live open/closed status computed from the store hours (`HOURS` constant, Eastern time),
scroll reveals, and the refill / ask-the-pharmacist forms, which open the visitor's email app because the site is static.

Store facts (addresses, phones, hours, services, products, prices) were taken from the pharmacy's own site and public listings. Verify time-sensitive details, such as vaccine availability and prices, before publishing.
