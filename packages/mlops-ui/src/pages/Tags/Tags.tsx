import React, { useEffect, useState } from 'react';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import projectPagesService from 'services/api/projectPages/projectPagesService';
import tagPagesService, {
  ITagRow,
} from 'services/api/tagPages/tagPagesService';

import { IProjectRef } from 'utils/projects/projects';
import { normalizeColor, validateTag } from 'utils/tags/tags';

import './Tags.scss';

function errorText(error: { message: string }): string {
  return error.message;
}

function TagRow({ tag, onChanged }: { tag: ITagRow; onChanged: () => void }) {
  const [name, setName] = useState(tag.name);
  const [color, setColor] = useState(tag.color ?? '');
  const [description, setDescription] = useState(tag.description ?? '');
  const [message, setMessage] = useState('');

  function save() {
    const problem = validateTag({ name, color: null, description });
    const normalized = normalizeColor(color);
    if (problem) {
      setMessage(problem);
      return;
    }
    if (normalized === undefined) {
      setMessage('A colour is a six-digit hex value such as #1f6feb.');
      return;
    }
    tagPagesService
      .updateTag(tag.id, {
        name: name.trim(),
        color: normalized,
        description: description || null,
      })
      .call()
      .then(() => {
        setMessage('Saved.');
        onChanged();
      })
      .catch((error) => setMessage(errorText(error)));
  }

  function remove() {
    if (
      !window.confirm(
        `Delete the tag "${tag.name}" and remove it from every run?`,
      )
    ) {
      return;
    }
    tagPagesService
      .deleteTag(tag.id)
      .call()
      .then(() => onChanged())
      .catch((error) => setMessage(errorText(error)));
  }

  return (
    <tr>
      <td>
        <input
          value={name}
          aria-label={`name of ${tag.name}`}
          onChange={(e) => setName(e.target.value)}
        />
      </td>
      <td>
        <input
          value={color}
          placeholder='#rrggbb'
          aria-label={`colour of ${tag.name}`}
          onChange={(e) => setColor(e.target.value)}
        />
      </td>
      <td>
        <input
          value={description}
          aria-label={`description of ${tag.name}`}
          onChange={(e) => setDescription(e.target.value)}
        />
      </td>
      <td className='Tags__actions'>
        <button type='button' onClick={save}>
          Save
        </button>
        <button type='button' onClick={remove}>
          Delete
        </button>
        {message && <span role='status'>{message}</span>}
      </td>
    </tr>
  );
}

function TagsOfProject({ project }: { project: IProjectRef }) {
  const [tags, setTags] = useState<ITagRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [color, setColor] = useState('');
  const [description, setDescription] = useState('');
  const [formMessage, setFormMessage] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setTags(null);
    const request = tagPagesService.getProjectTags(project.id);
    request
      .call()
      .then((data) => setTags(data))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`The tags could not be loaded: ${requestError.message}`);
        }
      });
    return () => request.abort();
  }, [project.id, reload]);

  function create(event: React.FormEvent) {
    event.preventDefault();
    const problem = validateTag({ name, color: null, description });
    const normalized = normalizeColor(color);
    if (problem) {
      setFormMessage(problem);
      return;
    }
    if (normalized === undefined) {
      setFormMessage('A colour is a six-digit hex value such as #1f6feb.');
      return;
    }
    tagPagesService
      .createTag(project.id, {
        name: name.trim(),
        color: normalized,
        description: description || null,
      })
      .call()
      .then(() => {
        setName('');
        setColor('');
        setDescription('');
        setFormMessage('Created.');
        setReload((n) => n + 1);
      })
      .catch((requestError) => setFormMessage(errorText(requestError)));
  }

  return (
    <>
      <h2>Tags in {project.slug}</h2>
      {error && (
        <p className='Tags__error' role='alert'>
          {error}
        </p>
      )}
      {tags && (
        <table className='Tags__table'>
          <thead>
            <tr>
              <th>Name</th>
              <th>Colour</th>
              <th>Description</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tags.map((tag) => (
              <TagRow
                key={`${tag.id}-${reload}`}
                tag={tag}
                onChanged={() => setReload((n) => n + 1)}
              />
            ))}
            {tags.length === 0 && (
              <tr>
                <td colSpan={4} className='Tags__muted'>
                  No tags yet. Create one below, or attach one to a run.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      <form
        className='Tags__create'
        onSubmit={create}
        aria-label='Create a tag'
      >
        <h3>New tag</h3>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Colour
          <input
            value={color}
            placeholder='#rrggbb'
            onChange={(e) => setColor(e.target.value)}
          />
        </label>
        <label>
          Description
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <button type='submit'>Create</button>
        {formMessage && <p role='status'>{formMessage}</p>}
      </form>
    </>
  );
}

// The tags of one project: create, rename, recolour, describe and delete.
function Tags(): React.FunctionComponentElement<React.ReactNode> {
  const [projects, setProjects] = useState<IProjectRef[] | null>(null);
  const [selected, setSelected] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const request = projectPagesService.getProjects();
    request
      .call()
      .then((data) => {
        setProjects(data);
        setSelected((current) => current || data[0]?.id || '');
      })
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`Projects could not be loaded: ${requestError.message}`);
        }
      });
    return () => request.abort();
  }, []);

  const project = projects?.find((p) => p.id === selected);
  return (
    <ErrorBoundary>
      <section className='Tags'>
        <h1>Tags</h1>
        {error && (
          <p className='Tags__error' role='alert'>
            {error}
          </p>
        )}
        {projects && projects.length === 0 && (
          <p className='Tags__muted'>
            You are not a member of any project yet.
          </p>
        )}
        {projects && projects.length > 0 && (
          <label className='Tags__project'>
            Project
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.slug}
                </option>
              ))}
            </select>
          </label>
        )}
        {project && <TagsOfProject key={project.id} project={project} />}
      </section>
    </ErrorBoundary>
  );
}

export default Tags;
