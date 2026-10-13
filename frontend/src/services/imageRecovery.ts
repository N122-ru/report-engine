import { canonicalImageName, deleteStoredImage, deleteStoredImageByName, getStoredImages, imageSha256, saveStoredImage } from './imageStore.ts';
import { fetchSessionImageAsFile, uploadSessionImages, type SessionImageItem } from './session.ts';

export const recoverSessionImages = async (
  token: string,
  serverImages: Pick<SessionImageItem, 'filename' | 'size_bytes' | 'mime_type' | 'sha256'>[],
  deletedNames: string[] = [],
): Promise<File[]> => {
  for (const filename of deletedNames) await deleteStoredImageByName(filename);
  const stored = await getStoredImages();
  const matchedNames = new Set<string>();
  const aliases = new Map<string, string[]>();
  const serverFiles: File[] = [];

  // Compare bytes before copying in either direction. A filename collision is a
  // conflict, not permission to replace a student's original.
  for (const image of serverImages) {
    const sameNameCount = serverImages.filter(other =>
      canonicalImageName(other.filename) === canonicalImageName(image.filename)).length;
    const matches = stored.filter(local => local.filename === image.filename || (
      sameNameCount === 1 && canonicalImageName(local.filename) === canonicalImageName(image.filename)
    ));
    let remote: File;
    const matchingLocal = matches.length === 1 ? matches[0] : undefined;
    if (matchingLocal && image.sha256 && matchingLocal.size === image.size_bytes && matchingLocal.sha256 === image.sha256) {
      remote = new File([matchingLocal.file], image.filename, {
        type: matchingLocal.file.type || image.mime_type,
        lastModified: matchingLocal.file.lastModified,
      });
      matchedNames.add(matchingLocal.filename);
    } else {
      const fetched = await fetchSessionImageAsFile(token, image.filename, image.mime_type);
      if (!fetched) throw new Error(`Не удалось получить изображение «${image.filename}» с сервера`);
      remote = fetched;
      if (remote.size !== image.size_bytes) {
        throw new Error(`Размер изображения «${image.filename}» не совпадает с манифестом сервера`);
      }
      const remoteHash = await imageSha256(remote);
      if (image.sha256 && remoteHash !== image.sha256) {
        throw new Error(`Серверное изображение «${image.filename}» не совпадает с манифестом`);
      }
      if (matches.some(local => local.size !== remote.size || local.sha256 !== remoteHash)) {
        throw new Error(`Локальное и серверное изображения «${image.filename}» различаются`);
      }
      matches.forEach(local => matchedNames.add(local.filename));
    }
    aliases.set(image.filename, matches.map(local => local.filename));
    serverFiles.push(remote);
  }

  for (const remote of serverFiles) {
    await saveStoredImage(remote);
    for (const filename of aliases.get(remote.name) || []) {
      if (filename !== remote.name) {
        await deleteStoredImage(filename);
      }
    }
  }

  const missing = stored.filter(local => !matchedNames.has(local.filename));
  if (missing.length === 0) return serverFiles;
  const uploaded = await uploadSessionImages(token, missing.map(local => local.file), true);
  const restored = uploaded.map((image, index) => {
    const original = missing[index].file;
    return new File([original], image.filename, {
      type: original.type, lastModified: original.lastModified,
    });
  });
  for (let index = 0; index < restored.length; index += 1) {
    await saveStoredImage(restored[index]);
    if (restored[index].name !== missing[index].filename) {
      await deleteStoredImage(missing[index].filename);
    }
  }
  return [...serverFiles, ...restored];
};
