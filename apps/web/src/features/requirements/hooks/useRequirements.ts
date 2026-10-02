import { useEffect, useState } from 'react';
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

  const fetchRequirements = async () => {
    try {
      setLoading(true);
      const data = await api.getRequirements(selectedProjectId || undefined);
      setRequirements(data);
      const id=initialRequirementId??recallEntity(selectedProjectId,'requirement');
      setSelectedReq(data.find(r=>r.id===id)??data[0]??null);
    } catch (err) {
      console.error('Failed to load requirements', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequirements();
  }, [selectedProjectId,initialRequirementId]);
  useEffect(()=>{if(selectedReq)rememberEntity(selectedReq.project_id,'requirement',selectedReq.id);},[selectedReq]);

  const createRequirement = async (data: RequirementCreate): Promise<Requirement | null> => {
    try {
      const created = await api.createRequirement({
        ...data,
        project_id: selectedProjectId || data.project_id || projects[0]?.id || '',
      });
      setRequirements([created, ...requirements]);
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
      setRequirements(requirements.map((r) => (r.id === reqId ? updated : r)));
      if (selectedReq?.id === reqId) {
        setSelectedReq(updated);
      }
    } catch (err) {
      console.error('Failed to update requirement status', err);
    }
  };

  const addImported = (imported: Requirement[]) => {
    setRequirements([...imported, ...requirements]);
    if (imported.length > 0) {
      setSelectedReq(imported[0]);
    }
  };

  return {
    requirements,
    loading,
    selectedReq,
    setSelectedReq,
    createRequirement,
    updateStatus,
    addImported,
  };
}
