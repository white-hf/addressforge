# 🎓 Advanced Guide: Learn Machine Learning by Customizing AddressForge

Welcome! If you are a technical newcomer or student eager to learn Machine Learning (ML) while building practical software, this guide is for you. 

AddressForge is a real-world **Entity Resolution & Address Normalization** system. By customizing it to parse and clean addresses for **your own country**, you will learn and apply key ML concepts: **Sentence Embeddings, Vector Search, Gradient Boosting (GBDTs), and Active Learning**.

---

## 📚 Core ML Concepts & Authoritative Resources

Here is the explanation of the machine learning techniques used in AddressForge, along with learning resources to study them:

### 1. Text Embeddings & Vector Search (文本嵌入与向量检索)
- **Concept**: Computes a numeric vector (e.g., 384 dimensions) representing the semantic meaning of a text. Similar texts (like "123 Main Street" and "123 Main St.") end up close to each other in vector space. We use **FAISS** (Facebook AI Similarity Search) to index millions of building reference coordinates/embeddings and search them in microseconds.
- **Underlying Models**: Transformer-based encoder model `BAAI/bge-small-en-v1.5` loaded via PyTorch.
- **Where to Learn**:
  - [Hugging Face NLP Course: Semantic Search](https://huggingface.co/learn/nlp-course/chapter5/5?fw=pt) (Authoritative & Interactive)
  - [Pinecone Vector Search Learning Center](https://www.pinecone.io/learn/vector-search/) (Excellent visual tutorials on FAISS/HNSW algorithms)
  - [SentenceTransformers Documentation](https://www.sbert.net/) (Official library docs)

### 2. Tabular Machine Learning & GBDTs (梯度提升树与表格数据模型)
- **Concept**: While Deep Learning dominates image/text generation, **Gradient Boosted Decision Trees (GBDTs)** are the state-of-the-art for tabular features (e.g., matching scores, edit distances, coordinate deltas). AddressForge uses **CatBoost** to rank candidate addresses (Pairwise Reranking) and calibrate accept/review confidence.
- **Where to Learn**:
  - [StatQuest: Gradient Boost Explained (YouTube Video)](https://www.youtube.com/watch?v=3CC4N4z3GJc) (Highly recommended for visual learners)
  - [CatBoost Official Tutorials & Docs](https://catboost.ai/en/docs/concepts/tutorials) (Practical hands-on notebooks)
  - [Machine Learning University - Tabular Data Course](https://mlu-explain.github.io/double-descent/) (Interactive visual articles on ML concepts)

### 3. Active Learning & Weak Supervision (主动学习与弱监督)
- **Concept**: Labeling data by hand is expensive. **Active Learning** selects the most ambiguous samples (where the ML model is confused) and prompts humans to label them. **Weak Supervision** uses heuristic regex rules to auto-generate noisy labels ("silver labels") to train initial models.
- **Where to Learn**:
  - [Active Learning Literature Survey by Burr Settles (PDF)](https://burrsettles.com/pub/settles.activelearning.pdf) (The academic bible of active learning)
  - [Snorkel: Weak Supervision & Programmatic Labeling](https://snorkel.org/) (Authoritative system for programmatic labeling)

---

## 🛠️ Step-by-Step Tutorial: Customizing AddressForge for Your Country

Follow these 4 steps to adapt this engine for your local country (e.g., Germany, UK, Japan, or Brazil).

### Step 1: Create a Localized Normalization Profile
AddressForge separates country-specific rules into the profile module under `src/addressforge/core/profiles/`.
1. Subclass the `BaseCountryProfile` interface defined in `src/addressforge/core/profiles/base.py`.
2. Implement your country's abbreviation mappings (e.g., replacing German `Str.` with `Strasse` or UK `Apt` with `Flat`).
3. Define your country's states/provinces and list of valid cities.
4. Register your new profile in `src/addressforge/core/profiles/factory.py`.

* **ML Learning Goal**: Learn text preprocessing, regex normalization, and domain-constraint alignment.

### Step 2: Ingest Reference Address Assets & Build Vector Index
To search addresses, the system needs a reference library.
1. Download public address datasets (e.g., OpenStreetMap, UK Ordnance Survey, or Germany Postcodes).
2. Format them into a CSV containing columns: `street_number`, `street_name`, `city`, `province`, `postal_code`, `reference_lat`, `reference_lon`.
3. Load them into the `external_building_reference` table using the importer (see `src/addressforge/core/reference.py`).
4. Generate the FAISS vector database for your country:
   ```bash
   # Computes dense embeddings using local BGE model and saves the index
   PYTHONPATH=src .venv/bin/python scripts/build_vector_index.py
   ```

* **ML Learning Goal**: Understand offline embedding inference, indexing vector arrays, and handling GPS/spatial metrics.

### Step 3: Run Shadow Pipeline & Gather Review Data
1. Run address queries from your company orders.
2. Open the Web Console (`http://127.0.0.1:8011`). The UI will show address results.
3. In the **Review Queue**, manually review and correct entries. Your corrections are saved into the `gold_label` table with `label_source = 'human'`.
4. Run this until you have collected a few hundred verified Gold Label records.

* **ML Learning Goal**: Experience human-in-the-loop (HITL) annotations, active learning data collection, and handling class imbalances.

### Step 4: Retrain CatBoost Classifier & Reranker Models
Now, train the models to specialize in your country's spatial and text patterns:
1. Run the Reranker trainer:
   ```bash
   # Generates pairwise samples (positive and hard negative candidates) and trains Reranker
   PYTHONPATH=src .venv/bin/python scripts/train_reranker_model.py
   ```
2. Run the Decision model calibration trainer:
   ```bash
   # Trains the decision boundaries to balance accept F1 vs review rate
   PYTHONPATH=src .venv/bin/python scripts/train_decision_model.py
   ```
3. Test your localized model:
   ```bash
   PYTHONPATH=src .venv/bin/pytest tests/
   ```

* **ML Learning Goal**: Master classification metrics (F1-score, Precision, Recall), pairwise ranking algorithms, loss optimization, and regression prevention.
