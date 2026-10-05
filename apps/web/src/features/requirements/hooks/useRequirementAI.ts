import { useState } from 'react';
import { useAIProgress } from '../../runtime/useAIProgress';
import { api } from '../../../api/client';
import {
  Requirement,
  RequirementAnalysisDTO,
  TestCaseGenerationItem,
  TestCasePriority,
  TestDesign,
  TestDesignCategory,
  TestDesignSuggestion,
} from '../../../types';

interface UseRequirementAIOptions {
  selectedReq: Requirement | null;
  onDesignCreated: (design: TestDesign) => void;
  onCaseCreated?: (testCaseId: string, testDesignId?: string) => void;
}

export function useRequirementAI({
  selectedReq,
  onDesignCreated,
  onCaseCreated,
}: UseRequirementAIOptions) {
  const [isAiAnalysisOpen, setIsAiAnalysisOpen] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<RequirementAnalysisDTO | null>(
    null,
  );
  const [analyzingReq, setAnalyzingReq] = useState(false);

  const [isAiDesignModalOpen, setIsAiDesignModalOpen] = useState(false);
  const [suggestedDesigns, setSuggestedDesigns] = useState<
    TestDesignSuggestion[]
  >([]);
  const [generatingDesigns, setGeneratingDesigns] = useState(false);

  const [isAiCaseModalOpen, setIsAiCaseModalOpen] = useState(false);
  const [suggestedCases, setSuggestedCases] = useState<
    TestCaseGenerationItem[]
  >([]);
  const [generatingCases, setGeneratingCases] = useState(false);
  const [activeDesignForCases, setActiveDesignForCases] =
    useState<TestDesign | null>(null);

  const analysisProgress = useAIProgress(selectedReq?.id ?? null);
  const designProgress = useAIProgress(selectedReq?.id ?? null);
  const caseProgress = useAIProgress(selectedReq?.id ?? null);

  const handleAnalyzeRequirementAI = async () => {
    if (!selectedReq) return;
    try {
      setAnalyzingReq(true);
      setAiAnalysis(null);
      setIsAiAnalysisOpen(true);
      const res = await analysisProgress.execute((onEvent, signal) =>
        api.streamRequirementAnalysis(selectedReq.id, onEvent, signal),
      );
      setAiAnalysis(res);
    } catch (err) {
      console.error('AI Requirement analysis failed', err);
    } finally {
      setAnalyzingReq(false);
    }
  };

  const handleGenerateDesignsAI = async () => {
    if (!selectedReq) return;
    try {
      setGeneratingDesigns(true);
      setSuggestedDesigns([]);
      setIsAiDesignModalOpen(true);
      const res = await designProgress.execute((onEvent, signal) =>
        api.streamTestDesigns(selectedReq.id, onEvent, signal),
      );
      setSuggestedDesigns(res);
    } catch (err) {
      console.error('AI Test Design generation failed', err);
    } finally {
      setGeneratingDesigns(false);
    }
  };

  const handleAdoptDesign = async (suggestion: TestDesignSuggestion) => {
    if (!selectedReq) return;
    try {
      const created = await api.createTestDesign({
        requirement_id: selectedReq.id,
        title: suggestion.title,
        category: suggestion.category as TestDesignCategory,
        description: suggestion.description,
        risk: suggestion.risk,
        status: 'DRAFT',
      });
      onDesignCreated(created);
      setSuggestedDesigns(
        suggestedDesigns.filter((s) => s.title !== suggestion.title),
      );
    } catch (err) {
      console.error('Failed to adopt test design', err);
    }
  };

  const handleGenerateCasesAI = async (design: TestDesign) => {
    try {
      setActiveDesignForCases(design);
      setGeneratingCases(true);
      setSuggestedCases([]);
      setIsAiCaseModalOpen(true);
      const res = await caseProgress.execute((onEvent, signal) =>
        api.streamTestCases(design.id, onEvent, signal),
      );
      setSuggestedCases(res);
    } catch (err) {
      console.error('AI Test Case generation failed', err);
    } finally {
      setGeneratingCases(false);
    }
  };

  const handleAdoptCase = async (item: TestCaseGenerationItem) => {
    if (!selectedReq || !activeDesignForCases) return;
    try {
      const created = await api.createTestCase({
        project_id: selectedReq.project_id,
        requirement_id: selectedReq.id,
        test_design_id: activeDesignForCases.id,
        title: item.title,
        preconditions: item.preconditions,
        steps: item.steps,
        expected_result: item.expected_result,
        // AI suggestions may carry a priority outside the union; the API persists it verbatim.
        priority: item.priority as TestCasePriority,
        tags: item.tags,
        automation_status: 'DRAFT',
      });
      onCaseCreated?.(created.id, created.test_design_id ?? activeDesignForCases.id);
      setSuggestedCases(suggestedCases.filter((c) => c.title !== item.title));
    } catch (err) {
      console.error('Failed to adopt test case', err);
    }
  };

  return {
    analysisProgress,
    designProgress,
    caseProgress,
    isAiAnalysisOpen,
    setIsAiAnalysisOpen,
    aiAnalysis,
    analyzingReq,
    isAiDesignModalOpen,
    setIsAiDesignModalOpen,
    suggestedDesigns,
    generatingDesigns,
    isAiCaseModalOpen,
    setIsAiCaseModalOpen,
    suggestedCases,
    generatingCases,
    activeDesignForCases,
    handleAnalyzeRequirementAI,
    handleGenerateDesignsAI,
    handleAdoptDesign,
    handleGenerateCasesAI,
    handleAdoptCase,
  };
}
