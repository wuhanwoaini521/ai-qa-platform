import { useEffect, useState } from 'react';
import { api } from '../../../api/client';
import { AutomationStatus, Project, TestCase, TestCaseCreate } from '../../../types';
import { recallEntity, rememberEntity } from '../../lifecycle/contextMemory';

interface UseTestCasesOptions {
  selectedProjectId: string | null;
  projects: Project[];
  initialTestCaseId?: string | null;
  emptySelectionWhenUnmatched?: boolean;
  onCaseSelected: (caseId: string) => void;
  onCaseListEmpty: () => void;
}

export function useTestCases({
  selectedProjectId,
  projects,
  initialTestCaseId,
  emptySelectionWhenUnmatched = false,
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
        const id = initialTestCaseId ?? (emptySelectionWhenUnmatched ? undefined : recallEntity(selectedProjectId, 'case'));
        const found = (id ? data.find((item) => item.id === id) : undefined)
          ?? (emptySelectionWhenUnmatched ? undefined : data[0]);
        if (found) {
          setSelectedCase(found);
          onCaseSelected(found.id);
        } else {
          setSelectedCase(null);
          onCaseListEmpty();
        }
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
  }, [selectedProjectId, initialTestCaseId, emptySelectionWhenUnmatched]);
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
