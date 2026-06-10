# Phase 1.1.1 — Gemini grey-zone re-judge vs. ollama baseline

## Scope & setup

- **213 grey-zone pairs** re-judged with Gemini (primary `gemini-2.5-pro`, fallback `gemini-2.5-flash`).
- Baseline: the Phase 1.1 merge (PR #2) judged these with ollama `qwen2.5:14b-instruct`. Source of pairs: the committed `phase1-merge-low-confidence.json`.
- **Caveat:** these 213 are the grey-zone pairs ollama labelled `parent_child` — the only slice persisted in the repo. The pairs ollama called `same`/`different`, and the full ~600-pair grey zone, were never committed and need the mac's nomic embeddings (absent on this host). So agreement here is measured **within the `parent_child` slice**.
- Identical eval: same pairs, same prompt wording (adapted to Gemini's JSON-schema mode), same definitions reconstructed from `raw/` (mostly `(none)`, exactly as ollama saw them), temperature 0.

## Headline

- **Agreement with ollama: 186/213 (87.3%)** (both say `parent_child`).
- Gemini reclassified **8** as `same` and **19** as `different`.
- Gemini verdict distribution: `parent_child`=186, `different`=19, `same`=8.
- ollama verdict distribution: `parent_child`=213.
- Errors/parse failures: 0.

## Cost

- **Total: $0.4788** of $5.00 cap.
- Models used: `gemini-2.5-pro`=213.
- Stopped on cap: False.

## Flipped → `same` (8) — synonyms ollama over-split

| A (src) | B (src) | sim | gemini conf | rationale |
|---|---|---:|---:|---|
| Anthropology, Medical (mesh) | medical anthropology (wikidata) | 0.938 | 1.0 | Both concepts describe the sub-field of anthropology that studies human health, beliefs, and social groups in relation to medicine. |
| Probability (arxiv) | Probability theory and stochastic processes (msc2020) | 0.912 | 1.0 | Both concepts are explicitly defined as the field covering the theory and applications of probability and stochastic processes. |
| Supersymmetric field theories in quantum mechanics (msc2020) | Supersymmetric field theories (physh) | 0.947 | 0.9 | Supersymmetric field theories are inherently quantum mechanical, making the phrase 'in quantum mechanics' redundant rather than a distinct sub-category. |
| spatial data (agris) | geo-spatial data (cso) | 0.941 | 0.9 | While 'geo-spatial' specifically refers to Earth, in most contexts, 'spatial data' is used interchangeably with it, as Earth is the default frame of reference. |
| osteonecrosis (agris) | Osteonecrosis, unspecified (icd) | 0.919 | 0.9 | Both terms refer to the general concept of bone death, with 'unspecified' in the ICD-10 context indicating the general form of the condition rather than a speci |
| sciences (agris) | science (wikidata) | 0.919 | 0.9 | The term 'sciences' is the plural form of 'science', and both concepts refer to the systematic endeavor of building and organizing knowledge. |
| animal sciences (agris) | Animal Science and Zoology (openalex) | 0.915 | 0.9 | Both terms refer to the broad scientific study of animals, with 'Animal Science' focusing on domestic animals and 'Zoology' on all animals, making the combined  |
| pigmentation disorders (agris) | Disorder of pigmentation, unspecified (icd) | 0.909 | 0.9 | Both terms refer to the general category of medical conditions affecting skin, hair, or eye coloration, with one being the plural form and the other a singular, |

## Flipped → `different` (19) — false neighbours

| A (src) | B (src) | sim | gemini conf | rationale |
|---|---|---:|---:|---|
| Trypanosoma gambiense (agris) | Gambiense trypanosomiasis (icd) | 0.949 | 1.0 | Trypanosoma gambiense is the protozoan parasite that causes the disease known as Gambiense trypanosomiasis (also called African sleeping sickness). |
| Taenia saginata (agris) | Taenia saginata taeniasis (icd) | 0.944 | 1.0 | "Taenia saginata" is the parasitic organism (beef tapeworm), whereas "Taenia saginata taeniasis" is the disease caused by an infection with that organism. |
| refractive index (agris) | refractive index measurement (cso) | 0.940 | 1.0 | One concept is a physical property (refractive index), while the other is the process or result of quantifying that property (refractive index measurement). |
| Plasmodium vivax (agris) | Plasmodium vivax malaria (icd) | 0.939 | 1.0 | Plasmodium vivax is the parasitic protozoan that causes the disease known as Plasmodium vivax malaria. |
| Yersinia enterocolitica (agris) | Enteritis due to Yersinia enterocolitica (icd) | 0.939 | 1.0 | One concept is a species of bacterium (Yersinia enterocolitica), while the other is a disease (enteritis) caused by that bacterium. |
| Trypanosoma rhodesiense (agris) | Rhodesiense trypanosomiasis (icd) | 0.938 | 1.0 | "Trypanosoma rhodesiense" is the parasitic protozoan that causes the disease known as "Rhodesiense trypanosomiasis" (East African sleeping sickness). |
| Plasmodium falciparum (agris) | Plasmodium falciparum malaria (icd) | 0.938 | 1.0 | "Plasmodium falciparum" is the parasitic protozoan that causes the disease "Plasmodium falciparum malaria". |
| Klebsiella pneumoniae (agris) | Pneumonia due to Klebsiella pneumoniae (icd) | 0.936 | 1.0 | Klebsiella pneumoniae is a species of bacteria, whereas pneumonia due to Klebsiella pneumoniae is the disease caused by that bacterium. |
| Streptococcus pneumoniae (agris) | Pneumonia due to Streptococcus pneumoniae (icd) | 0.928 | 1.0 | One concept is a species of bacterium (Streptococcus pneumoniae), while the other is a disease (Pneumonia) caused by that bacterium. |
| soil pollution (agris) | Exposure to soil pollution (icd) | 0.917 | 1.0 | One concept is an environmental condition ('soil pollution'), while the other is the event of an organism coming into contact with that condition ('Exposure to  |
| Echinococcus multilocularis (agris) | Echinococcus multilocularis infection, unspecified (icd) | 0.914 | 1.0 | One concept is the parasitic organism 'Echinococcus multilocularis', while the other is the disease or 'infection' caused by that organism. |
| Schistosoma japonicum (agris) | Schistosomiasis due to Schistosoma japonicum (icd) | 0.913 | 1.0 | Schistosoma japonicum is the parasitic organism, whereas Schistosomiasis is the disease caused by that organism. |
| Brucella melitensis (agris) | Brucellosis due to Brucella melitensis (icd) | 0.912 | 1.0 | Brucella melitensis is the bacterium that causes the disease known as Brucellosis. |
| Brucella abortus (agris) | Brucellosis due to Brucella abortus (icd) | 0.910 | 1.0 | Brucella abortus is the bacterial species that acts as the causative agent for the disease known as Brucellosis. |
| Cosmology (physh) | history of cosmology (wikidata) | 0.910 | 1.0 | One concept is a scientific discipline, while the other is the historical study of that discipline. |
| factors (agris) | Classification of factors (msc2020) | 0.920 | 0.9 | Concept A, 'factors', is a very general term for influences or components, while Concept B, 'Classification of factors', refers to the mathematical or theoretic |
| disabilities (agris) | people with disabilities (cso) | 0.915 | 0.9 | One concept refers to the conditions ('disabilities'), while the other refers to the individuals who have those conditions ('people with disabilities'). |
| polarimetry (agris) | polarimetric data (cso) | 0.909 | 0.9 | Polarimetry is the scientific technique or method, while polarimetric data is the information or measurements produced by that technique. |
| energy conservation (agris) | conservation of energy resources (cso) | 0.909 | 0.8 | "Energy conservation" typically refers to the physical principle that energy cannot be created or destroyed, whereas "conservation of energy resources" refers t |

## Low Gemini confidence (<0.6) — genuine edge cases (0)

_none_


## Kept as `parent_child` (186)

Gemini confirmed ollama on 186 pairs. Sample (first 15):

| A (src) | B (src) | sim | gemini conf | rationale |
|---|---|---:|---:|---|
| gait (agris) | walking gait (cso) | 0.949 | 1.0 | "Gait" is the general pattern of limb movement, while "walking gait" is a specific type of gait. |
| digestive system diseases (agris) | Other diseases of digestive system (icd) | 0.947 | 0.9 | Concept A, 'digestive system diseases', is a broad category that encompasses Concept B, 'Other diseases of digestive system', which is a residual subcategory fo |
| text mining (agris) | text mining techniques (cso) | 0.947 | 0.9 | "Text mining" is the broad field of study, while "text mining techniques" refers to the specific methods and algorithms used within that field. |
| metabolic disorders (agris) | Other metabolic disorders (icd) | 0.947 | 1.0 | The term "Other metabolic disorders" is a specific subcategory used for classification within the broader category of "metabolic disorders". |
| geomorphology (agris) | tectonic geomorphology (wikidata) | 0.946 | 1.0 | Tectonic geomorphology is a specific subfield within the broader discipline of geomorphology that focuses on the effects of tectonic activity on landforms. |
| pericarditis (agris) | Infective pericarditis (icd) | 0.946 | 1.0 | Pericarditis is the general inflammation of the pericardium, while infective pericarditis is a specific type of pericarditis caused by an infection. |
| hormone antagonists (agris) | Other and unspecified hormone antagonists (icd) | 0.946 | 1.0 | Concept B, "Other and unspecified hormone antagonists," is a specific subcategory used for classification within the broader, more general category of "hormone  |
| dairy science (agris) | Animal and dairy science (oecd-fos) | 0.945 | 1.0 | "Animal and dairy science" is a broader field that encompasses "dairy science" as one of its components. |
| spinal cord diseases (agris) | Other diseases of spinal cord (icd) | 0.945 | 0.9 | Concept A, 'spinal cord diseases', is a broad category that encompasses Concept B, 'Other diseases of spinal cord', which is a residual subcategory for diseases |
| oesophageal diseases (agris) | Other specified diseases of oesophagus (icd) | 0.942 | 0.9 | "Oesophageal diseases" is a broad category that includes all diseases of the oesophagus, while "Other specified diseases of oesophagus" is a specific sub-catego |
| Pathology, pathophysiology (msc2020) | Pathophysiology (scopus-asjc) | 0.942 | 0.9 | Pathology is the study of disease in general, while pathophysiology is a subfield of pathology that focuses specifically on the functional changes associated wi |
| eigenfunctions (agris) | eigenvalues and eigenfunctions (cso) | 0.942 | 1.0 | Eigenfunctions are one component of the broader concept of 'eigenvalues and eigenfunctions', which encompasses both mathematical entities. |
| pneumoconiosis (agris) | Unspecified pneumoconiosis (icd) | 0.942 | 0.9 | The term 'pneumoconiosis' is a general category of lung disease, while 'Unspecified pneumoconiosis' is a specific diagnostic code used when the type of pneumoco |
| laryngotracheitis (agris) | Acute laryngotracheitis (icd) | 0.941 | 0.9 | Acute laryngotracheitis is a specific form of laryngotracheitis, distinguished by its sudden onset and short duration. |
| respiratory disorders (agris) | Other respiratory disorders (icd) | 0.941 | 1.0 | The category 'respiratory disorders' is a broad parent class that encompasses the more specific sub-category 'Other respiratory disorders'. |
