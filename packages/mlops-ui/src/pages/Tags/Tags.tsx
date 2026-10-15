import React, { useEffect, useState } from 'react';

import { MenuItem } from '@material-ui/core';

import { Badge, Button, Card, Table, Text } from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import OutlinedField from 'components/OutlinedField/OutlinedField';

import projectPagesService from 'services/api/projectPages/projectPagesService';
import tagPagesService, {
  ITagRow,
} from 'services/api/tagPages/tagPagesService';

import { IProjectRef } from 'utils/projects/projects';
import { normalizeColor, validateTag } from 'utils/tags/tags';

import './Tags.scss';

const COLOUR_HINT = 'A colour is a six-digit hex value such as #1f6feb.';

function errorText(error: { message: string }): string {
  return error.message;
}

interface ITagFields {
  name: string;
  color: string;
  description: string;
}

// The name, colour and description fields, shared by the create and edit forms.
function TagFields({
  fields,
  onChange,
}: {
  fields: ITagFields;
  onChange: (next: ITagFields) => void;
}) {
  return (
    <div className='Tags__fields'>
      <OutlinedField
        id='tag-name'
        label='Name'
        value={fields.name}
        onChange={(e) => onChange({ ...fields, name: e.target.value })}
      />
      <OutlinedField
        id='tag-colour'
        label='Colour'
        placeholder='#rrggbb'
        value={fields.color}
        onChange={(e) => onChange({ ...fields, color: e.target.value })}
      />
      <OutlinedField
        id='tag-description'
        label='Description'
        value={fields.description}
        onChange={(e) => onChange({ ...fields, description: e.target.value })}
      />
    </div>
  );
}

// Checks the fields and returns the message for the first problem, or null.
function checkFields(fields: ITagFields): string | null {
  const problem = validateTag({
    name: fields.name,
    color: null,
    description: fields.description,
  });
  if (problem) {
    return problem;
  }
  return normalizeColor(fields.color) === undefined ? COLOUR_HINT : null;
}

function toBody(fields: ITagFields) {
  return {
    name: fields.name.trim(),
    color: normalizeColor(fields.color) ?? null,
    description: fields.description || null,
  };
}

// Edits one tag. Deleting asks for a second click, because the tag is removed from every run.
function EditTagCard({
  tag,
  onChanged,
  onDeleted,
}: {
  tag: ITagRow;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const [fields, setFields] = useState<ITagFields>({
    name: tag.name,
    color: tag.color ?? '',
    description: tag.description ?? '',
  });
  const [message, setMessage] = useState('');
  const [confirming, setConfirming] = useState(false);

  function save() {
    const problem = checkFields(fields);
    if (problem) {
      setMessage(problem);
      return;
    }
    tagPagesService
      .updateTag(tag.id, toBody(fields))
      .call()
      .then(() => {
        setMessage('Saved.');
        onChanged();
      })
      .catch((error) => setMessage(errorText(error)));
  }

  function remove() {
    tagPagesService
      .deleteTag(tag.id)
      .call()
      .then(() => onDeleted())
      .catch((error) => {
        setConfirming(false);
        setMessage(errorText(error));
      });
  }

  return (
    <Card
      title={`Edit “${tag.name}”`}
      subtitle='Changes apply to every run with this tag.'
    >
      <TagFields fields={fields} onChange={setFields} />
      <div className='Tags__actions'>
        <Button variant='contained' onClick={save}>
          Save
        </Button>
        {confirming ? (
          <>
            <Text size={12} color='error'>
              Remove the tag from every run?
            </Text>
            <Button
              variant='outlined'
              color='secondary'
              className='Tags__destructive'
              onClick={remove}
            >
              Delete tag
            </Button>
            <Button variant='text' onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </>
        ) : (
          <Button
            variant='outlined'
            className='Tags__destructive'
            onClick={() => setConfirming(true)}
          >
            Delete
          </Button>
        )}
        {message && (
          <Text size={12} tint={70} role='status'>
            {message}
          </Text>
        )}
      </div>
    </Card>
  );
}

function TagsOfProject({ project }: { project: IProjectRef }) {
  const [tags, setTags] = useState<ITagRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fields, setFields] = useState<ITagFields>({
    name: '',
    color: '',
    description: '',
  });
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

  const selected = tags?.find((tag) => tag.id === selectedId);

  function create(event: React.FormEvent) {
    event.preventDefault();
    const problem = checkFields(fields);
    if (problem) {
      setFormMessage(problem);
      return;
    }
    tagPagesService
      .createTag(project.id, toBody(fields))
      .call()
      .then(() => {
        setFields({ name: '', color: '', description: '' });
        setFormMessage('Created.');
        setReload((n) => n + 1);
      })
      .catch((requestError) => setFormMessage(errorText(requestError)));
  }

  return (
    <>
      {error && (
        <Text size={12} color='error' role='alert'>
          {error}
        </Text>
      )}
      <Card
        title={`Tags in ${project.slug}`}
        subtitle='Select a tag to edit it.'
      >
        {tags && (
          <Table
            columns={[
              { key: 'name', label: 'Name' },
              { key: 'colour', label: 'Colour' },
              { key: 'description', label: 'Description' },
            ]}
            rows={tags.map((tag) => ({
              id: tag.id,
              name: (
                <Badge label={tag.name} color={tag.color ?? ''} size='small' />
              ),
              colour: <span className='Tags__mono'>{tag.color ?? '–'}</span>,
              description: tag.description ?? '–',
            }))}
            rowKey='id'
            onRowClick={setSelectedId}
            selectedRowKey={selectedId ?? undefined}
            emptyText='No tags yet. Create one below, or attach one to a run.'
          />
        )}
      </Card>
      {selected && (
        <EditTagCard
          key={selected.id}
          tag={selected}
          onChanged={() => setReload((n) => n + 1)}
          onDeleted={() => {
            setSelectedId(null);
            setReload((n) => n + 1);
          }}
        />
      )}
      <Card title='New tag'>
        <form
          className='Tags__create'
          onSubmit={create}
          aria-label='Create a tag'
        >
          <TagFields fields={fields} onChange={setFields} />
          <div className='Tags__actions'>
            <Button variant='contained' type='submit'>
              Create tag
            </Button>
            {formMessage && (
              <Text size={12} tint={70} role='status'>
                {formMessage}
              </Text>
            )}
          </div>
        </form>
      </Card>
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
        <header className='Tags__header'>
          <Text component='h1' size={18} weight={600} tint={100}>
            Tags
          </Text>
          <Text size={12} tint={50}>
            Tags group runs within a project. Changing a tag changes it on every
            run.
          </Text>
        </header>
        {error && (
          <Text size={12} color='error' role='alert'>
            {error}
          </Text>
        )}
        {projects && projects.length === 0 && (
          <Text size={12} tint={50}>
            You are not a member of any project yet.
          </Text>
        )}
        {projects && projects.length > 0 && (
          <div className='Tags__project'>
            <OutlinedField
              id='tag-project'
              label='Project'
              select
              value={selected}
              onValueChange={setSelected}
            >
              {projects.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.slug}
                </MenuItem>
              ))}
            </OutlinedField>
          </div>
        )}
        {project && <TagsOfProject key={project.id} project={project} />}
      </section>
    </ErrorBoundary>
  );
}

export default Tags;
