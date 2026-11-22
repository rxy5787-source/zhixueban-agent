import { localRecordId } from './attempt'

export type LocalLibrary = { id: string; name: string }
export type LocalMaterial = { id: string; libraryId: string; name: string; file: Blob }
export type LocalAttempt = { id: string; questionId: string; answer: number; correct: boolean; time: number }
export type OfflineData = { libraries: LocalLibrary[]; materials: LocalMaterial[]; attempts: LocalAttempt[] }

type StoreName = keyof OfflineData
let connection: Promise<IDBDatabase> | undefined

function database() {
  connection ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('zhixueban-offline-study', 1)
    let blocked = false
    request.onblocked = () => {
      blocked = true
      reject(new Error('本地数据库被另一个页面占用，请关闭其他知学伴标签页后重试。'))
    }
    request.onupgradeneeded = () => {
      const db = request.result
      db.createObjectStore('libraries', { keyPath: 'id' })
      db.createObjectStore('materials', { keyPath: 'id' }).createIndex('libraryId', 'libraryId')
      db.createObjectStore('attempts', { keyPath: 'id' })
    }
    request.onerror = () => reject(request.error)
    request.onsuccess = () => {
      const db = request.result
      if (blocked) { db.close(); return }
      db.onversionchange = () => { db.close(); connection = undefined }
      resolve(db)
    }
  }).catch(error => { connection = undefined; throw error })
  return connection
}

function result<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function readOfflineData(): Promise<OfflineData> {
  const db = await database()
  const tx = db.transaction(['libraries', 'materials', 'attempts'])
  const [libraries, materials, attempts] = await Promise.all([
    result<LocalLibrary[]>(tx.objectStore('libraries').getAll()),
    result<LocalMaterial[]>(tx.objectStore('materials').getAll()),
    result<LocalAttempt[]>(tx.objectStore('attempts').getAll()),
  ])
  return { libraries, materials, attempts: attempts.sort((a, b) => b.time - a.time) }
}

async function write(names: StoreName[], action: (tx: IDBTransaction) => void) {
  const db = await database()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(names, 'readwrite')
    tx.oncomplete = () => resolve()
    tx.onabort = () => reject(tx.error ?? new Error('学习空间内容已变化，请刷新后重试。'))
    try { action(tx) } catch (error) { tx.abort(); reject(error) }
  })
}

export const addLibrary = (name: string) => write(['libraries'], tx => {
  tx.objectStore('libraries').add({ id: localRecordId(), name })
})

export const renameLibrary = (id: string, name: string) => write(['libraries'], tx => {
  const store = tx.objectStore('libraries')
  const existing = store.getKey(id)
  existing.onsuccess = () => { if (existing.result) store.put({ id, name }); else tx.abort() }
})

export const deleteLibrary = (id: string) => write(['libraries', 'materials'], tx => {
  tx.objectStore('libraries').delete(id)
  const store = tx.objectStore('materials')
  const keys = store.index('libraryId').getAllKeys(id)
  keys.onsuccess = () => { for (const key of keys.result) store.delete(key) }
})

export const addMaterials = (libraryId: string | null, files: File[]) => write(['libraries', 'materials'], tx => {
  const libraries = tx.objectStore('libraries')
  const destination = libraryId ?? 'study-inbox'
  const existing = libraries.getKey(destination)
  existing.onsuccess = () => {
    if (!existing.result && libraryId !== null) { tx.abort(); return }
    if (!existing.result) libraries.add({ id: destination, name: '学习资料' })
    const materials = tx.objectStore('materials')
    for (const file of files) materials.add({ id: localRecordId(), libraryId: destination, name: file.name, file })
  }
})

export const deleteMaterial = (id: string) => write(['materials'], tx => { tx.objectStore('materials').delete(id) })
export const saveAttempt = (attempt: LocalAttempt) => write(['attempts'], tx => { tx.objectStore('attempts').put(attempt) })
