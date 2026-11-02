export type LicenseStatus = 'open' | 'check' | 'restricted';

const RESTRICTED = /proprietary|all rights reserved/i;
const OPEN =
  /^(the )?(mit(-0)?|isc|0bsd|unlicense|cc0-1\.0|apache[- ]2(\.0)?|bsd-[23]-clause|mpl-2\.0|(a|l)?gpl-[23]\.[01](-only|-or-later)?)( license)?$/i;

/** 아는 오픈소스 라이선스만 open으로 본다. 나머지 자유 문구는 사람이 확인해야 한다. */
export function licenseStatus(license: string | null): LicenseStatus {
  if (!license) return 'check';
  if (RESTRICTED.test(license)) return 'restricted';
  return OPEN.test(license.trim()) ? 'open' : 'check';
}

export function licenseNotice(license: string | null): string | null {
  const status = licenseStatus(license);
  if (status === 'open') return null;
  if (status === 'restricted') {
    return '이 스킬은 독점 라이선스라 설치 명령을 제공하지 않습니다. 사용 조건은 스킬 폴더나 저장소 루트의 LICENSE 파일에서 확인하세요.';
  }
  if (!license) {
    return '라이선스가 명시되지 않았습니다. 이 경우 저작권자의 허락 없이는 복제나 수정이 제한될 수 있으니, 설치 전에 스킬 폴더와 저장소를 확인하세요.';
  }
  return '라이선스 조건을 확인하지 못했습니다. 설치 전에 스킬 폴더나 저장소 루트의 LICENSE 파일을 확인하세요.';
}
