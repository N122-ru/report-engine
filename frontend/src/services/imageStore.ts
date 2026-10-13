const DATABASE_NAME = 'report-local-images';
const STORE_NAME = 'originals';

interface ImageRecord {
  filename: string;
  blob: Blob;
  type: string;
  lastModified: number;
  size: number;
  sha256: string;
}

export interface StoredImage {
  filename: string;
  file: File;
  size: number;
  sha256: string;
}

export const canonicalImageName = (filename: string): string =>
  filename.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

let databasePromise: Promise<IDBDatabase> | null = null;

const openDatabase = (): Promise<IDBDatabase> => {
  if (databasePromise) return databasePromise;
  const pending = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME, { keyPath: 'filename' });
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => {
        db.close();
        databasePromise = null;
      };
      resolve(db);
    };
    request.onerror = () => reject(request.error);
  });
  databasePromise = pending.catch(error => {
    databasePromise = null;
    throw error;
  });
  return databasePromise;
};

const requestResult = <T>(request: IDBRequest<T>): Promise<T> => new Promise((resolve, reject) => {
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
});

const completeTransaction = (transaction: IDBTransaction): Promise<void> => new Promise((resolve, reject) => {
  transaction.oncomplete = () => resolve();
  transaction.onabort = () => reject(transaction.error);
  transaction.onerror = () => reject(transaction.error);
});

export const imageSha256 = async (image: Blob): Promise<string> => {
  const hash = await crypto.subtle.digest('SHA-256', await image.arrayBuffer());
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
};

export const saveStoredImage = async (file: File): Promise<void> => {
  const db = await openDatabase();
  const sha256 = await imageSha256(file);
  const record: ImageRecord = {
    filename: file.name, blob: file, type: file.type,
    lastModified: file.lastModified, size: file.size, sha256,
  };
  const transaction = db.transaction(STORE_NAME, 'readwrite');
  const completed = completeTransaction(transaction);
  const store = transaction.objectStore(STORE_NAME);
  let conflict: Error | null = null;
  const lookup = store.get(file.name);
  lookup.onsuccess = () => {
    const existing = lookup.result as ImageRecord | undefined;
    if (!existing) {
      store.add(record);
    } else if (existing.sha256 !== sha256 || existing.size !== file.size) {
      conflict = new Error(`Изображение «${file.name}» уже сохранено с другими данными`);
      transaction.abort();
    }
  };
  await completed.catch(error => { throw conflict || error; });
};

export const getStoredImages = async (): Promise<StoredImage[]> => {
  const db = await openDatabase();
  const records = await requestResult<ImageRecord[]>(
    db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).getAll(),
  );
  return Promise.all(records.map(async record => {
    if (record.blob.size !== record.size || await imageSha256(record.blob) !== record.sha256) {
      throw new Error(`Локальное изображение «${record.filename}» не прошло проверку целостности`);
    }
    return {
      filename: record.filename, size: record.size, sha256: record.sha256,
      file: new File([record.blob], record.filename, {
        type: record.type, lastModified: record.lastModified,
      }),
    };
  }));
};

export const deleteStoredImage = async (filename: string): Promise<void> => {
  const db = await openDatabase();
  const transaction = db.transaction(STORE_NAME, 'readwrite');
  const completed = completeTransaction(transaction);
  transaction.objectStore(STORE_NAME).delete(filename);
  await completed;
};

export const deleteStoredImageFile = async (file: File): Promise<void> => {
  const hash = await imageSha256(file);
  const stored = await getStoredImages();
  const exact = stored.find(item => item.filename === file.name);
  if (exact && exact.sha256 !== hash) {
    throw new Error(`Изображение «${file.name}» изменилось после выбора файла`);
  }
  for (const image of stored) {
    if (canonicalImageName(image.filename) === canonicalImageName(file.name)
        && image.sha256 === hash) {
      await deleteStoredImage(image.filename);
    }
  }
};

export const deleteStoredImageByName = async (filename: string): Promise<void> => {
  const stored = await getStoredImages();
  const exact = stored.find(image => image.filename === filename);
  const matches = stored.filter(image => canonicalImageName(image.filename) === canonicalImageName(filename));
  if (!exact && new Set(matches.map(image => image.sha256)).size > 1) {
    throw new Error(`Имя «${filename}» соответствует нескольким локальным изображениям`);
  }
  for (const image of matches) {
    if (!exact || image.sha256 === exact.sha256) await deleteStoredImage(image.filename);
  }
};
