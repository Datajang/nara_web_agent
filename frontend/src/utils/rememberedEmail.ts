// 로그인 '이메일 기억하기' (2026-11-24 운영 피드백). 이 브라우저에 이메일 주소만 남긴다.
// 비밀번호·토큰은 저장하지 않는다(§9: 토큰은 httpOnly 쿠키만). 저장소가 막혀도(사생활 보호 창) 로그인은 된다.
const KEY = 'nara.login.email'

export function readRememberedEmail(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveRememberedEmail(email: string): void {
  try {
    localStorage.setItem(KEY, email)
  } catch {
    // 저장할 수 없으면 이번에는 기억하지 않는다
  }
}

export function forgetRememberedEmail(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // 저장소가 막혀 있으면 지울 것도 없다
  }
}
