import json
import os
import numpy as np
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.callbacks import EarlyStopping

MAX_LEN = 16000
NPZ_PATH = "Data.npz"
WEIGHTS_PATH = "model.weights.h5"
CONFIG_PATH = "model_config.json"
HISTORY_PATH = "history.json"
CLASS_COUNTS_PATH = "train_class_counts.json"
VALID_TOP5_PATH = "valid_top5.json"
LABEL_PATH = "label_to_id.json"

def load_data(path=NPZ_PATH):
    data = np.load(path, allow_pickle=True)
    train_x = np.array(data["train_x"])
    train_y = data["train_y"]
    valid_x = np.array(data["valid_x"])
    valid_y = data["valid_y"]
    all_labels = sorted(set(str(v) for v in np.ravel(train_y)) | set(str(v) for v in np.ravel(valid_y)))
    label_to_id = {v: i for i, v in enumerate(all_labels)}
    n_classes = len(label_to_id)
    train_y = np.array([label_to_id[str(v)] for v in np.ravel(train_y)], dtype=np.int32)
    valid_y = np.array([label_to_id[str(v)] for v in np.ravel(valid_y)], dtype=np.int32)
    return train_x, train_y, valid_x, valid_y, n_classes, label_to_id

def pad_normalize(x_list, max_len=MAX_LEN):
    out = np.zeros((len(x_list), max_len), dtype=np.float32)
    for i in range(len(x_list)):
        s = np.array(x_list[i], dtype=np.float32).flatten()
        s = s / (np.max(np.abs(s)) + 1e-8)
        out[i, :min(len(s), max_len)] = s[:max_len]
    return out

def build_model(max_len, n_classes):
    model = keras.Sequential([
        layers.Input(shape=(max_len, 1)),
        layers.Conv1D(64, 15, activation="relu", padding="same"),
        layers.MaxPooling1D(4),
        layers.Conv1D(128, 7, activation="relu", padding="same"),
        layers.MaxPooling1D(4),
        layers.Flatten(),
        layers.Dense(128, activation="relu"),
        layers.Dropout(0.4),
        layers.Dense(n_classes, activation="softmax")
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model

def main():
    train_x, train_y, valid_x, valid_y, n_classes, label_to_id = load_data()
    train_x = pad_normalize(list(train_x))
    valid_x = pad_normalize(list(valid_x))
    train_x = np.expand_dims(train_x, -1)
    valid_x = np.expand_dims(valid_x, -1)
    model = build_model(MAX_LEN, n_classes)
    early = EarlyStopping(monitor="val_loss", patience=8, restore_best_weights=True)
    history = model.fit(train_x, train_y, validation_data=(valid_x, valid_y), epochs=50, batch_size=32, callbacks=[early], verbose=1)
    model.save_weights(WEIGHTS_PATH)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"max_len": MAX_LEN, "n_classes": n_classes}, f)
    with open(LABEL_PATH, "w", encoding="utf-8") as f:
        json.dump(label_to_id, f, indent=2)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump({"epochs": list(range(1, len(history.history["val_accuracy"]) + 1)), "val_accuracy": [float(x) for x in history.history["val_accuracy"]]}, f, indent=2)
    u, c = np.unique(train_y, return_counts=True)
    with open(CLASS_COUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump({int(k): int(v) for k, v in zip(u, c)}, f, indent=2)
    vu, vc = np.unique(valid_y, return_counts=True)
    top5 = np.argsort(vc)[-5:][::-1]
    with open(VALID_TOP5_PATH, "w", encoding="utf-8") as f:
        json.dump({int(vu[i]): int(vc[i]) for i in top5}, f, indent=2)
    print("Веса сохранены:", WEIGHTS_PATH)
    print("Конфиг:", CONFIG_PATH)

if __name__ == "__main__":
    main()
