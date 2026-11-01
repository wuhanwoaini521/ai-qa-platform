import { useEffect, useState } from 'react';
import { APIError } from '../../../api/errors';
import { api } from '../../../api/client';
import { Project, Requirement, RequirementCreate, RequirementStatus } from '../../../types';
import { recallEntity, rememberEntity } from '../../lifecycle/contextMemory';

interface UseRequirementsOptions {
  selectedProjectId: string | null;
  projects: Project[];
  initialRequirementId?: string | null;
}

export function useRequirements({
  selectedProjectId,
  projects,
  initialRequirementId,
}: UseRequirementsOptions) {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReq, setSelectedReq] = useState<Requirement | null>(null);
  const [loadError, setLoadError] = useState<'forbidden' | 'failed' | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    setRequirements([]);
    setSelectedReq(null);
    void api.getRequirements(selectedProjectId || undefined).then((data) => {
      if (!active) return;
      setRequirements(data);
      const id = initialRequirementId ?? recallEntity(selectedProjectId, 'requirement');
      setSelectedReq(data.find((requirement) => requirement.id === id) ?? data[0] ?? null);
    }).catch((err: unknown) => {
      if (!active) return;
      console.error('Failed to load requirements', err);
      setLoadError(err instanceof APIError && err.status === 403 ? 'forbidden' : 'failed');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [selectedProjectId, initialRequirementId, reloadVersion]);

  const refresh = () => setReloadVersion((version) => version + 1);
  useEffect(()=>{if(selectedReq)rememberEntity(selectedReq.project_id,'requirement',selectedReq.id);},[selectedReq]);

  const createRequirement = async (data: RequirementCreate): Promise<Requirement | null> => {
    try {
      const created = await api.createRequirement({
        ...data,
        project_id: selectedProjectId || data.project_id || projects[0]?.id || '',
      });
      setRequirements((current) => [created, ...current]);
      setSelectedReq(created);
      return created;
    } catch (err) {
      console.error('Failed to create requirement', err);
      return null;
    }
  };

  const updateStatus = async (reqId: string, status: RequirementStatus) => {
    try {
      const updated = await api.updateRequirement(reqId, { status });
      setRequirements((current) => current.map((r) => (r.id === reqId ? updated : r)));
      if (selectedReq?.id === reqId) {
        setSelectedReq(updated);
      }
    } catch (err) {
      console.error('Failed to update requirement status', err);
    }
  };

  const addImported = (imported: Requirement[]) => {
    setRequirements((current) => [...imported, ...current]);
    if (imported.length > 0) {
      setSelectedReq(imported[0]);
    }
  };

  return {
    requirements,
    loading,
    loadError,
    refresh,
    selectedReq,
    setSelectedReq,
    createRequirement,
    updateStatus,
    addImported,
  };
}
