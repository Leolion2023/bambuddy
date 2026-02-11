import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { X, Package, Loader2, CheckCircle, XCircle, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { SliceJobStatus } from '../api/client';
import { Button } from './Button';
import { useToast } from '../contexts/ToastContext';

interface SliceFileModalProps {
  fileId?: number;
  archiveId?: number;
  fileName: string;
  onClose: () => void;
}

export function SliceFileModal({ fileId, archiveId, fileName, onClose }: SliceFileModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [filamentPresetId, setFilamentPresetId] = useState<number | undefined>();
  const [printerPresetId, setPrinterPresetId] = useState<number | undefined>();
  const [processPresetId, setProcessPresetId] = useState<number | undefined>();
  const [autoPushToArchive, setAutoPushToArchive] = useState(true);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Fetch OrcaSlicer status
  const { data: status } = useQuery({
    queryKey: ['orcaslicer-status'],
    queryFn: api.getOrcaSlicerStatus,
  });

  // Fetch available profiles
  const { data: profiles, isLoading: profilesLoading } = useQuery({
    queryKey: ['orcaslicer-profiles'],
    queryFn: api.getOrcaSlicerProfiles,
  });

  // Poll job status if we have an active job
  const { data: jobStatus } = useQuery({
    queryKey: ['orcaslicer-job', currentJobId],
    queryFn: () => api.getSliceJob(currentJobId!),
    enabled: !!currentJobId,
    refetchInterval: (data) => {
      // Stop polling if job is done
      if (!data) return 2000;
      const status = data as SliceJobStatus;
      return status.status === 'completed' || status.status === 'failed' ? false : 2000;
    },
  });

  // Submit slicing job
  const sliceMutation = useMutation({
    mutationFn: () =>
      api.sliceFile({
        file_id: fileId,
        archive_id: archiveId,
        filament_preset_id: filamentPresetId,
        printer_preset_id: printerPresetId,
        process_preset_id: processPresetId,
        auto_push_to_archive: autoPushToArchive,
      }),
    onSuccess: (data) => {
      setCurrentJobId(data.job_id);
      showToast(t('orcaslicer.messages.jobCreated'));
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    sliceMutation.mutate();
  };

  const handleClose = () => {
    // Invalidate archives if job completed successfully
    if (jobStatus?.status === 'completed' && autoPushToArchive) {
      queryClient.invalidateQueries({ queryKey: ['archives'] });
    }
    onClose();
  };

  const isSlicing = currentJobId && jobStatus && jobStatus.status === 'processing';
  const isCompleted = jobStatus?.status === 'completed';
  const isFailed = jobStatus?.status === 'failed';

  // Check if OrcaSlicer is available
  if (status && !status.available) {
    return (
      <div
        className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
        onClick={onClose}
      >
        <div
          className="bg-bambu-dark-secondary rounded-xl border border-bambu-dark-tertiary w-full max-w-md p-6"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-3 mb-4">
            <XCircle className="w-6 h-6 text-red-500" />
            <h2 className="text-lg font-semibold text-white">
              {t('orcaslicer.status.notAvailable')}
            </h2>
          </div>
          <p className="text-bambu-gray mb-4">{status.message}</p>
          <Button onClick={onClose} variant="primary" className="w-full">
            {t('common.close')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={handleClose}
    >
      <div
        className="bg-bambu-dark-secondary rounded-xl border border-bambu-dark-tertiary w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-bambu-dark-tertiary">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full bg-bambu-green/20 text-bambu-green">
              <Package className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">{t('orcaslicer.title')}</h2>
              <p className="text-sm text-bambu-gray truncate max-w-[300px]">{fileName}</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="text-bambu-gray hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Show job progress if slicing */}
          {currentJobId && jobStatus ? (
            <div className="space-y-4">
              {/* Status */}
              <div className="flex items-center gap-3">
                {isSlicing && <Loader2 className="w-5 h-5 text-bambu-green animate-spin" />}
                {isCompleted && <CheckCircle className="w-5 h-5 text-green-500" />}
                {isFailed && <XCircle className="w-5 h-5 text-red-500" />}
                {!isSlicing && !isCompleted && !isFailed && <Clock className="w-5 h-5 text-bambu-gray" />}
                <div className="flex-1">
                  <div className="text-white font-medium">
                    {t(`orcaslicer.jobs.${jobStatus.status}`)}
                  </div>
                  {jobStatus.error_message && (
                    <div className="text-sm text-red-400">{jobStatus.error_message}</div>
                  )}
                </div>
              </div>

              {/* Progress bar */}
              {isSlicing && (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-bambu-gray">{t('orcaslicer.jobs.progress')}</span>
                    <span className="text-white">{jobStatus.progress}%</span>
                  </div>
                  <div className="h-2 bg-bambu-dark rounded-full overflow-hidden">
                    <div
                      className="h-full bg-bambu-green transition-all duration-300"
                      style={{ width: `${jobStatus.progress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Output info */}
              {isCompleted && jobStatus.output_filename && (
                <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                  <div className="text-sm text-green-400">
                    {autoPushToArchive
                      ? t('orcaslicer.messages.pushedToArchive')
                      : t('orcaslicer.messages.slicingComplete')}
                  </div>
                  <div className="text-xs text-bambu-gray mt-1">{jobStatus.output_filename}</div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                <Button onClick={handleClose} variant="primary" className="flex-1">
                  {t('common.close')}
                </Button>
              </div>
            </div>
          ) : (
            /* Show form if not slicing yet */
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-sm text-red-400">
                  {error}
                </div>
              )}

              {profilesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-bambu-green" />
                </div>
              ) : (
                <>
                  {/* Filament Preset */}
                  <div>
                    <label className="block text-sm text-bambu-gray mb-1">
                      {t('orcaslicer.profiles.filament')} {t('orcaslicer.profiles.optional')}
                    </label>
                    <select
                      value={filamentPresetId || ''}
                      onChange={(e) => setFilamentPresetId(e.target.value ? Number(e.target.value) : undefined)}
                      className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                    >
                      <option value="">{t('orcaslicer.profiles.selectFilament')}</option>
                      {profiles?.filament.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} {p.filament_type && `(${p.filament_type})`}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Printer Preset */}
                  <div>
                    <label className="block text-sm text-bambu-gray mb-1">
                      {t('orcaslicer.profiles.printer')} {t('orcaslicer.profiles.optional')}
                    </label>
                    <select
                      value={printerPresetId || ''}
                      onChange={(e) => setPrinterPresetId(e.target.value ? Number(e.target.value) : undefined)}
                      className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                    >
                      <option value="">{t('orcaslicer.profiles.selectPrinter')}</option>
                      {profiles?.printer.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Process Preset */}
                  <div>
                    <label className="block text-sm text-bambu-gray mb-1">
                      {t('orcaslicer.profiles.process')} {t('orcaslicer.profiles.optional')}
                    </label>
                    <select
                      value={processPresetId || ''}
                      onChange={(e) => setProcessPresetId(e.target.value ? Number(e.target.value) : undefined)}
                      className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                    >
                      <option value="">{t('orcaslicer.profiles.selectProcess')}</option>
                      {profiles?.process.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Auto-push to Archive */}
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="auto-push"
                      checked={autoPushToArchive}
                      onChange={(e) => setAutoPushToArchive(e.target.checked)}
                      className="w-4 h-4 rounded border-bambu-dark-tertiary bg-bambu-dark text-bambu-green focus:ring-bambu-green focus:ring-offset-0"
                    />
                    <label htmlFor="auto-push" className="text-sm text-white cursor-pointer">
                      {t('orcaslicer.settings.autoPushToArchive')}
                    </label>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 pt-2">
                    <Button
                      type="button"
                      onClick={handleClose}
                      variant="secondary"
                      className="flex-1"
                    >
                      {t('common.cancel')}
                    </Button>
                    <Button
                      type="submit"
                      variant="primary"
                      className="flex-1"
                      disabled={sliceMutation.isPending}
                    >
                      {sliceMutation.isPending ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          {t('orcaslicer.actions.slicing')}
                        </>
                      ) : (
                        t('orcaslicer.actions.startSlicing')
                      )}
                    </Button>
                  </div>
                </>
              )}
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
