import { useEffect, useState } from 'react';
import { api } from '../../../api/client';
import { AutomationStatus, Project, TestCase, TestCaseCreate } from '../../../types';
import { recallEntity, rememberEntity } from '../../lifecycle/contextMemory';

interface UseTestCasesOptions {
  selectedProjectId: string | null;
  projects: Project[];
  initialTestCaseId?: string | null;
  onCaseSelected: (caseId: string) => void;
  onCaseListEmpty: () => void;
}

export function useTestCases({
  selectedProjectId,
  projects,
  initialTestCaseId,
  onCaseSelected,
  onCaseListEmpty,
}: UseTestCasesOptions) {
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState<TestCase | null>(null);

  const fetchTestCases = async () => {
    try {
      setLoading(true);
      const data = await api.getTestCases(selectedProjectId || undefined);
      setTestCases(data);
      if (data.length > 0) {
        const id=initialTestCaseId??recallEntity(selectedProjectId,'case');
        const found=data.find(c=>c.id===id)??data[0];
        setSelectedCase(found);
        onCaseSelected(found.id);
      } else {
        setSelectedCase(null);
        onCaseListEmpty();
      }
    } catch (err) {
      console.error('Failed to load test cases', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTestCases();
  }, [selectedProjectId,initialTestCaseId]);
  useEffect(()=>{if(selectedCase)rememberEntity(selectedCase.project_id,'case',selectedCase.id);},[selectedCase]);

  const createTestCase = async (data: TestCaseCreate): Promise<TestCase | null> => {
    try {
      const created = await api.createTestCase({
        ...data,
        project_id: selectedProjectId || data.project_id || projects[0]?.id || '',
      });
      setTestCases([created, ...testCases]);
      setSelectedCase(created);
      return created;
    } catch (err) {
      console.error('Failed to create test case', err);
      return null;
    }
  };

  const updateStatus = async (caseId: string, automationStatus: AutomationStatus) => {
    try {
      const updated = await api.updateTestCase(caseId, { automation_status: automationStatus });
      setTestCases(testCases.map((tc) => (tc.id === caseId ? updated : tc)));
      if (selectedCase?.id === caseId) {
        setSelectedCase(updated);
      }
    } catch (err) {
      console.error('Failed to update automation status', err);
    }
  };

  return { testCases, loading, selectedCase, setSelectedCase, createTestCase, updateStatus };
}
