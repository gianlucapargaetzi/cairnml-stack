import {
  INoteReqBody,
  INote,
  INotesList,
} from 'types/services/models/notes/notes';
import { IApiRequest } from 'types/services/services';

import API from '../api';

// A run has one note: the `notes` field of the run (/api/v1/runs/{id}). The fork's notes list
// therefore holds at most one entry, with id 0.
const NOTE_ID = 0;

function runPath(runId: string) {
  return `v1/runs/${runId}`;
}

function toNote(run: any, name = 'Note'): INote {
  return {
    id: NOTE_ID,
    name,
    content: run.notes ?? '',
    created_at: run.created_at,
  };
}

function mapped<T, R>(
  request: IApiRequest<T>,
  fn: (value: T) => R,
): IApiRequest<R> {
  return {
    call: async (detail?: any) => fn(await request.call(detail)),
    abort: request.abort,
  };
}

function getNotes(runId: string): IApiRequest<INotesList> {
  return mapped(API.get<any>(runPath(runId)), (run: any) =>
    run.notes ? [toNote(run)] : [],
  );
}

function createNote(runId: string, reqBody: INoteReqBody): IApiRequest<INote> {
  return mapped(
    API.patch<any>(runPath(runId), { notes: reqBody.content }),
    (run) => toNote(run, reqBody.name),
  );
}

function getSingleNote(runId: string, noteId: number): IApiRequest<INote> {
  return mapped(API.get<any>(runPath(runId)), (run: any) => toNote(run));
}

function updateNote(
  runId: string,
  noteId: number,
  reqBody: INoteReqBody,
): IApiRequest<any> {
  return mapped(
    API.patch<any>(runPath(runId), { notes: reqBody.content }),
    (run) => toNote(run, reqBody.name),
  );
}

function deleteNote(runId: string, noteId: number): IApiRequest<any> {
  return mapped(API.patch<any>(runPath(runId), { notes: null }), () => ({
    deleted: NOTE_ID,
  }));
}

const notesService = {
  getNotes,
  getSingleNote,
  createNote,
  updateNote,
  deleteNote,
};

export default notesService;
