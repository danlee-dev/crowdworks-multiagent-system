# -*- coding: utf-8 -*-
import json
import re
from collections import defaultdict, Counter
import tiktoken

# 파일 경로
INPUT_DIR = 'datas'
OUTPUT_DIR = 'preprocessed_datas'

# 토큰 계산용 인코더 (OpenAI tiktoken)
try:
	tokenizer = tiktoken.get_encoding("cl100k_base")
except:
	tokenizer = None


def clean_essential_only(text):
	"""최소한의 텍스트 정리 (양끝 공백 제거만)"""
	if not text:
		return text
	return text.strip()


def is_meaningful_data(item):
	"""의미있는 데이터인지 판단"""
	page_content = item.get('page_content', '').strip()
	meta_data = item.get('meta_data', {})
	item_label = meta_data.get('item_label', '')
	
	# 1. 빈 내용
	if not page_content:
		return False
	
	# 2. 목차 패턴 (표 목록)
	if "<표" in page_content and "···" in page_content:
		return False
	
	# 3. 너무 짧은 텍스트 - hierarchy 병합 후 적용
	if item_label == "text" and len(page_content) < 30:
		return False
	
	# 4. 숫자/기호만 있는 내용
	if re.match(r'^[\d\s\-\|\.\·\(\)]+$', page_content):
		return False
		
	return True


def merge_hierarchy_chunks(documents):
	"""hierarchy 관계에 있는 item들을 하나의 chunk로 합치기 (크기 제한 적용)"""
	
	# chunk_id로 문서 매핑
	doc_map = {}
	for doc in documents:
		chunk_id = doc['meta_data']['chunk_id']
		doc_map[chunk_id] = doc
	
	# hierarchy 관계 분석
	hierarchy_groups = defaultdict(list)
	orphans = []  # hierarchy 없는 독립 문서들
	used_as_parent = set()  # 부모로 사용된 문서들 추적
	
	for doc in documents:
		hierarchy = doc['meta_data'].get('hierarchy')
		if hierarchy:
			hierarchy_groups[hierarchy].append(doc)
			# 부모 문서 추적
			used_as_parent.add(hierarchy)
		else:
			orphans.append(doc)
	
	print(f"Hierarchy 병합: {len(hierarchy_groups)}개 그룹, {len(orphans)}개 후보 독립 문서")
	print(f"부모로 사용된 문서: {len(used_as_parent)}개")
	
	merged_documents = []
	
	# 1. Hierarchy 그룹들을 합치기 (크기 제한 적용)
	for parent_chunk_id, children in hierarchy_groups.items():
		parent_doc = doc_map.get(parent_chunk_id)
		
		if not parent_doc:
			print(f"⚠️ 부모 문서를 찾을 수 없음: {parent_chunk_id}")
			# 자식들을 개별적으로 처리
			merged_documents.extend(children)
			continue
		
		# 자식들을 index 순으로 정렬
		children_sorted = sorted(children, key=lambda x: x['meta_data']['index'])
		
		# 모든 자식들을 하나로 병합 (크기 제한 없음)
		merged_doc = create_single_merged_chunk(parent_doc, children_sorted)
		merged_documents.append(merged_doc)
	
	# 2. 독립 문서들 추가 (부모로 사용되지 않은 것들만)
	actual_orphans = []
	for doc in orphans:
		chunk_id = doc['meta_data']['chunk_id']
		if chunk_id not in used_as_parent:
			actual_orphans.append(doc)
	
	for doc in actual_orphans:
		# name 필드 설정: table은 별도 처리, 나머지는 제목 추출
		name = ""
		item_label = doc['meta_data']['item_label']
		original_page_content = doc['page_content']
		
		if item_label == 'text':
			name = extract_title_from_content(doc['page_content'])
			processed_content = clean_essential_only(doc['page_content'])  # 필수 정리 적용
			
		elif item_label == 'table':
			# 독립 테이블의 경우
			name = extract_table_title_from_content(doc['page_content'])
			processed_content = optimize_table_for_search(doc['page_content'])
			# 원본 정보를 merged_children에 저장 (독립 문서도 동일한 구조)
			doc['meta_data']['merged_children'] = [{
				'item_label': 'table',
				'chunk_id': doc['meta_data']['chunk_id'],
				'content': doc['meta_data'].get('original_page_content', original_page_content),  # 완전 원본
				'summary': doc['meta_data'].get('summary', '')  # 원래 table summary 사용
			}]
			
		else:
			name = extract_title_from_content(doc['page_content'])
			processed_content = clean_essential_only(doc['page_content'])  # 필수 정리 적용
		
		merged_doc = {
			"page_content": processed_content,
			"name": name,
			"meta_data": doc['meta_data']
		}
		merged_documents.append(merged_doc)
	
	print(f"실제 독립 문서: {len(actual_orphans)}개 (중복 제거: {len(orphans) - len(actual_orphans)}개)")
	print(f"Hierarchy 병합 완료: {len(merged_documents)}개 문서")
	return merged_documents


def extract_table_title_from_content(content):
	"""표 내용에서 제목 추출 시도 (HTML 테이블 캡션 또는 기존 형식 지원)"""
	if not content:
		return ""
	
	# HTML 테이블에서 caption 추출
	caption_match = re.search(r'<caption[^>]*>(.*?)</caption>', content, re.IGNORECASE | re.DOTALL)
	if caption_match:
		caption = caption_match.group(1).strip()
		# HTML 태그 제거
		caption = re.sub(r'<[^>]+>', '', caption)
		if caption:
			return caption
	
	# 기존 <표 X-X> 패턴도 지원 (하위 호환성)
	lines = content.strip().split('\n')
	for line in lines:
		if '<표' in line and '>' in line:
			title = re.sub(r'<표[^>]*>', '', line)
			title = title.replace('|', '').strip()
			if title:
				return title
	
	return ""


def create_single_merged_chunk(parent_doc, children, suffix=""):
	"""단일 merged 청크 생성"""
	# 합쳐진 content 생성
	merged_content = create_merged_content(parent_doc, children)
	
	# chunk_id 생성
	base_chunk_id = parent_doc['meta_data']['chunk_id']
	new_chunk_id = f"{base_chunk_id}{suffix}" if suffix else base_chunk_id
	
	# 새로운 merged document 생성
	merged_doc = {
		"page_content": merged_content,
		"name": extract_title_from_content(parent_doc['page_content']),  # 부모 제목이 name
		"meta_data": create_merged_metadata(parent_doc, children, new_chunk_id)
	}
	
	return merged_doc


def optimize_table_for_search(table_content):
	"""표 내용을 임베딩/검색에 최적화된 형태로 변환 (HTML 테이블 지원)"""
	if not table_content:
		return table_content
	
	# HTML 테이블인지 확인
	if '<table' in table_content.lower():
		return optimize_html_table_for_search(table_content)
	else:
		# 기존 파이프 구분자 형식 처리 (하위 호환성)
		return optimize_pipe_table_for_search(table_content)


def optimize_html_table_for_search(table_content):
	"""HTML 테이블을 단순 나열 방식으로 변환 (데이터 정확성 우선)"""
	optimized_parts = []
	
	# 캡션 추출
	caption = ""
	caption_match = re.search(r'<caption[^>]*>(.*?)</caption>', table_content, re.IGNORECASE | re.DOTALL)
	if caption_match:
		caption = re.sub(r'<[^>]+>', '', caption_match.group(1)).strip()
		if caption:
			optimized_parts.append(f"표제목: {caption}")
	
	# tbody가 있으면 tbody 내용, 없으면 전체 테이블에서 tr 추출
	tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', table_content, re.IGNORECASE | re.DOTALL)
	if tbody_match:
		content_to_parse = tbody_match.group(1)
	else:
		content_to_parse = table_content
	
	# 모든 tr 태그에서 내용 추출 (헤더/데이터 구분 없이)
	tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', content_to_parse, re.IGNORECASE | re.DOTALL)
	
	row_parts = []
	row_num = 1
	for tr_content in tr_matches:
		# 모든 셀(th, td) 내용 추출
		cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr_content, re.IGNORECASE | re.DOTALL)
		
		# 셀 내용 정리
		cleaned_cells = []
		for cell in cells:
			cell_text = re.sub(r'<[^>]+>', '', cell).strip()
			if cell_text:  # 비어있지 않은 셀만 추가
				cleaned_cells.append(clean_table_cell(cell_text))
		
		# 유효한 데이터가 있는 행만 추가
		if cleaned_cells:
			# 임베딩 최적화: 행 번호와 구분자 제거, 공백으로만 구분
			row_content = " ".join(cleaned_cells)
			row_parts.append(row_content)
			row_num += 1
	
	# 제목과 행들을 줄바꿈으로 구분하여 연결
	if optimized_parts and row_parts:
		return optimized_parts[0] + "\n" + "\n".join(row_parts)
	elif row_parts:
		return "\n".join(row_parts)
	else:
		return ' '.join(optimized_parts) if optimized_parts else ""


def optimize_pipe_table_for_search(table_content):
	"""기존 파이프 구분자 테이블 처리 (하위 호환성)"""
	lines = table_content.strip().split('\n')
	optimized_parts = []
	
	for line in lines:
		if '|' in line:
			# 표 라인: 구분자 완전 제거하고 압축
			cells = [cell.strip() for cell in line.split('|') if cell.strip()]
			if cells:
				# 임베딩 최적화: 공백과 특수문자 최소화
				cleaned_cells = []
				for cell in cells:
					cleaned = clean_table_cell(cell)
					cleaned_cells.append(cleaned)
				optimized_parts.append(' '.join(cleaned_cells))
		else:
			# 표가 아닌 라인 (제목, 출처 등)
			cleaned_line = line.strip()
			if cleaned_line and not re.match(r'^[\-\+\|\s]+$', cleaned_line):
				optimized_parts.append(cleaned_line)
	
	return ' '.join(optimized_parts)


def clean_table_cell(cell_content):
	"""테이블 셀 내용 정리 (숫자 쉼표 제거, 공백 압축)"""
	if not cell_content:
		return ""
	
	# 숫자에서 쉼표 제거, 공백 압축
	cleaned = cell_content.replace(',', '').replace('  ', ' ').strip()
	return cleaned


def create_merged_content(parent_doc, children):
	"""부모와 자식들의 content를 하나로 합치기 (검색 최적화)"""
	
	# 부모 content로 시작 (필수 정리 적용)
	parent_content = clean_essential_only(parent_doc['page_content'])
	content_parts = [parent_content]
	
	for child in children:
		item_label = child['meta_data']['item_label']
		child_content = child['page_content']  # 원본 상태
		
		if item_label == 'table':
			# 검색 최적화된 표 내용을 page_content에 추가
			optimized_table = optimize_table_for_search(child_content)
			content_parts.append(f"\n{optimized_table}")
			
		elif item_label == 'text':
			# 추가 텍스트 (출처, 주석 등) - 필수 정리 적용
			if child_content.strip():
				cleaned_text = clean_essential_only(child_content)
				content_parts.append(f"\n{cleaned_text}")
	
	return '\n'.join(content_parts)


def extract_title_from_content(content):
	"""content에서 제목 추출 (최소한의 정리만)"""
	if not content:
		return ""
	
	lines = content.strip().split('\n')
	if lines:
		# 마크다운 헤더 제거만
		title = lines[0].replace('#', '').strip()
		return title
	return ""


def create_merged_metadata(parent_doc, children, chunk_id):
	"""합쳐진 문서의 metadata 생성"""
	
	# 부모의 metadata를 기본으로 사용
	merged_meta = parent_doc['meta_data'].copy()
	
	# chunk_id 업데이트
	merged_meta['chunk_id'] = chunk_id
	
	# item_label을 "merged"로 변경
	merged_meta['item_label'] = 'merged'
	
	# 자식들의 정보를 merged_children에 통합 (content와 summary 포함)
	merged_children = []
	
	for child in children:
		child_meta = {
			'item_label': child['meta_data']['item_label'],
			'chunk_id': child['meta_data']['chunk_id'],
			'content': child['meta_data'].get('original_page_content', child['page_content'])  # 완전 원본 내용
		}
		
		# table인 경우 summary 추가 (원래 table summary 사용)
		if child['meta_data']['item_label'] == 'table':
			child_meta['summary'] = child['meta_data'].get('summary', '')
		
		merged_children.append(child_meta)
	
	merged_meta['merged_children'] = merged_children
	merged_meta['merged_count'] = len(children) + 1  # 부모 포함
	
	# 페이지 범위 계산
	all_pages = set(parent_doc['meta_data']['page_number'])
	for child in children:
		all_pages.update(child['meta_data']['page_number'])
	
	merged_meta['page_number'] = sorted(list(all_pages))
	
	return merged_meta


def count_tokens(text):
	"""텍스트의 토큰 수 계산"""
	if not text or not tokenizer:
		# tiktoken이 없으면 대략적으로 계산 (한국어: 1글자 ≈ 1.5 토큰)
		return int(len(text) * 1.5)
	
	try:
		return len(tokenizer.encode(text))
	except:
		return int(len(text) * 1.5)


# ===== 페이지 단위 텍스트 청킹 =====

def chunk_texts_by_page(documents):
	"""
	동일 페이지 내에서 연속된 text item들을 하나의 청크로 묶는다.
	표(table)는 항상 별도의 청크로 유지한다.
	사이사이에 표가 있으면 텍스트 청크를 끊어서 [text_chunk, table, text_chunk] 순서를 유지한다.
	"""
	print(f"\n=== 📝 Step 4: 페이지 단위 텍스트 청킹 시작 ===")
	print(f"입력 문서: {len(documents)}개")
	
	# 텍스트 문서에 토큰 수 부여 (hierarchy 없는 독립 text 대상)
	prepared_docs = []
	for doc in documents:
		label = doc['meta_data']['item_label']
		if label == 'text' and not doc['meta_data'].get('hierarchy'):
			doc['meta_data']['token_count'] = count_tokens(doc['page_content'])
		prepared_docs.append(doc)
	
	# 전체 문서를 index 기준으로 정렬하여 순서 보존
	ordered_docs = sorted(prepared_docs, key=lambda x: x['meta_data']['index'])
	
	final_docs = []
	buffer = []  # 연속 텍스트 버퍼
	current_page = None
	
	def flush_text_buffer():
		"""버퍼에 모인 텍스트로 chunked_text 생성 후 final_docs에 추가"""
		nonlocal buffer
		if not buffer:
			return
		# create_single_chunk 동작과 유사하게 병합
		content_parts = [t['page_content'] for t in buffer]
		merged_content = '\n\n'.join(content_parts)
		base_meta = buffer[0]['meta_data'].copy()
		chunk_meta = {
			'chunk_id': buffer[0]['meta_data']['chunk_id'],
			'item_label': 'chunked_text',
			'chunked_from': [t['meta_data']['chunk_id'] for t in buffer],
			'chunked_count': len(buffer),
			'index': buffer[0]['meta_data']['index'],
			'page_number': sorted(list(set().union(*[t['meta_data']['page_number'] for t in buffer]))),
			'document_id': base_meta.get('document_id'),
			'hierarchy': None,
			'token_count': count_tokens(merged_content),
		}
		# base_meta와 병합 (기본 필드 유지)
		for k, v in base_meta.items():
			if k not in chunk_meta:
				chunk_meta[k] = v
		chunk_doc = {
			"page_content": merged_content,
			"name": extract_title_from_content(buffer[0]['page_content']),
			"meta_data": chunk_meta
		}
		final_docs.append(chunk_doc)
		buffer = []
	
	for doc in ordered_docs:
		label = doc['meta_data']['item_label']
		pages = doc['meta_data'].get('page_number', [])
		page = pages[0] if isinstance(pages, list) and pages else None
		
		if label == 'text' and not doc['meta_data'].get('hierarchy'):
			# 동일 페이지 내 연속 텍스트는 하나로
			if buffer and current_page is not None and page != current_page:
				# 페이지가 바뀌면 버퍼 flush
				flush_text_buffer()
			current_page = page
			buffer.append(doc)
		else:
			# 텍스트가 아닌 요소를 만나면, 버퍼를 먼저 flush 후 그대로 추가
			flush_text_buffer()
			current_page = None
			final_docs.append(doc)
	
	# 남은 버퍼 flush
	flush_text_buffer()
	
	print(f"청킹 완료: {len(final_docs)}개 문서")
	text_chunk_count = len([d for d in final_docs if d['meta_data']['item_label'] == 'chunked_text'])
	print(f"  - 생성된 텍스트 청크: {text_chunk_count}개")
	return final_docs


def analyze_final_results(final_docs):
	"""최종 결과 분석"""
	
	print(f"\n=== 📊 최종 전처리 결과 분석 ===")
	print(f"최종 문서 수: {len(final_docs)}")
	
	# item_label별 통계
	label_counts = Counter(doc['meta_data']['item_label'] for doc in final_docs)
	
	for label, count in label_counts.items():
		print(f"{label}: {count}개")
	
	# merged 및 chunked 문서들의 상세 정보
	merged_docs = [doc for doc in final_docs if doc['meta_data']['item_label'] == 'merged']
	chunked_docs = [doc for doc in final_docs if doc['meta_data']['item_label'] == 'chunked_text']
	
	if merged_docs:
		print(f"\n=== 🔗 합쳐진 문서 상세 (상위 10개) ===")
		
		# 크기별 분포
		size_distribution = {'small': 0, 'medium': 0, 'large': 0}
		
		for i, doc in enumerate(merged_docs, 1):
			name = doc.get('name', '제목 없음')
			merged_count = doc['meta_data'].get('merged_count', 1)
			content_length = len(doc['page_content'])
			
			# 크기 분류
			if content_length < 1000:
				size_category = 'small'
			elif content_length < 3000:
				size_category = 'medium'
			else:
				size_category = 'large'
			size_distribution[size_category] += 1
			
			if i <= 10:  # 처음 10개만 상세 출력
				print(f"{i}. {name}")
				print(f"   - 합쳐진 항목 수: {merged_count}")
				print(f"   - 내용 길이: {content_length}자 ({size_category})")
				
				# 자식 정보
				children = doc['meta_data'].get('merged_children', [])
				child_types = Counter(child['item_label'] for child in children)
				child_info = ', '.join(f"{k}:{v}" for k, v in child_types.items())
				print(f"   - 포함 요소: {child_info}")
		
		print(f"\n=== 📏 Merged 청크 크기 분포 ===")
		print(f"Small (<1K자): {size_distribution['small']}개")
		print(f"Medium (1K-3K자): {size_distribution['medium']}개") 
		print(f"Large (>3K자): {size_distribution['large']}개")
	
	# chunked 문서들의 상세 정보
	if chunked_docs:
		print(f"\n=== 🔗 Chunked 문서 상세 (상위 10개) ===")
		
		# 크기별 분포
		chunked_size_distribution = {'small': 0, 'medium': 0, 'large': 0}
		
		for i, doc in enumerate(chunked_docs, 1):
			name = doc.get('name', '제목 없음')
			chunked_count = doc['meta_data'].get('chunked_count', 1)
			content_length = len(doc['page_content'])
			token_count = doc['meta_data'].get('token_count', 0)
			
			# 크기 분류
			if content_length < 1000:
				size_category = 'small'
			elif content_length < 3000:
				size_category = 'medium'
			else:
				size_category = 'large'
			chunked_size_distribution[size_category] += 1
			
			if i <= 10:  # 처음 10개만 상세 출력
				print(f"{i}. {name}")
				print(f"   - 합쳐진 text 수: {chunked_count}")
				print(f"   - 내용 길이: {content_length}자 ({size_category})")
				print(f"   - 토큰 수: {token_count}")
		
		print(f"\n=== 📏 Chunked 텍스트 크기 분포 ===")
		print(f"Small (<1K자): {chunked_size_distribution['small']}개")
		print(f"Medium (1K-3K자): {chunked_size_distribution['medium']}개") 
		print(f"Large (>3K자): {chunked_size_distribution['large']}개")


def process_single_file(input_file_path, output_file_path, doc_metadata_no_toc):
	"""단일 파일을 전처리하는 함수 (페이지 단위 텍스트 청킹 버전)"""
	print(f"\n=== 📂 파일 처리 시작: {input_file_path} ===")
	
	with open(input_file_path, 'r', encoding='utf-8') as f:
		data = json.load(f)

	documents = data['documents']
	doc_metadata = data.get('metadata', {})
	
	# 현재 파일의 document_title 가져오기
	current_document_title = doc_metadata.get('document_title', '')
	print(f"원본 문서: {len(documents)}개")
	print(f"문서 제목: {current_document_title}")

	# Step 0: picture 태그 데이터 필터링
	non_picture_docs = []
	picture_count = 0
	for doc in documents:
		item_label = doc.get('meta_data', {}).get('item_label', '')
		if item_label == 'picture':
			picture_count += 1
		else:
			non_picture_docs.append(doc)
	
	print(f"Step 0 완료: picture 데이터 제거 ({picture_count}개 제거, {len(non_picture_docs)}개 남음)")

	# Step 1: 기본 전처리 (metadata 합치기 + 원본 보존)
	preprocessed = []
	for doc in non_picture_docs:
		merged_meta = doc.get('meta_data', {}).copy()
		merged_meta.update(doc_metadata_no_toc)
		
		# 원본 page_content 보존
		original_page_content = doc.get('page_content', '')
		
		# page_content는 전처리 적용
		processed_page_content = clean_essential_only(original_page_content)
		
		# summary도 필수 정리만
		if 'summary' in merged_meta and merged_meta['summary']:
			merged_meta['summary'] = clean_essential_only(merged_meta['summary'])
		
		# 원본을 meta_data에 저장
		merged_meta['original_page_content'] = original_page_content
		
		# meta_data의 document_title을 현재 파일의 올바른 값으로 업데이트
		if current_document_title:
			merged_meta['document_title'] = current_document_title
		
		preprocessed.append({
			'page_content': processed_page_content,  # 전처리된 내용
			'embedding': None,
			'meta_data': merged_meta
		})

	print(f"Step 1 완료: 기본 전처리 + 원본 보존 ({len(preprocessed)}개)")

	# Step 2: Hierarchy 병합 (제목-표 매칭 포함)
	merged_docs = merge_hierarchy_chunks(preprocessed)
	print(f"Step 2 완료: Hierarchy 병합 ({len(merged_docs)}개)")

	# Step 3: 의미없는 데이터 필터링 (짧은 text 포함)
	filtered_docs = [doc for doc in merged_docs if is_meaningful_data(doc)]
	print(f"Step 3 완료: 필터링 ({len(filtered_docs)}개, 제거: {len(merged_docs) - len(filtered_docs)}개)")

	# Step 4: 페이지 단위 텍스트 청킹
	chunked_docs = chunk_texts_by_page(filtered_docs)
	print(f"Step 4 완료: 페이지 단위 텍스트 청킹 ({len(chunked_docs)}개)")

	# Step 5: 제목을 page_content에 추가
	final_docs = []
	for doc in chunked_docs:
		doc_copy = doc.copy()
		current_document_title = doc_copy['meta_data'].get('document_title', '')
		
		if current_document_title:
			# document_title을 page_content 맨 앞에 추가
			doc_copy['page_content'] = f"{current_document_title}\n\n{doc_copy['page_content']}"
		
		final_docs.append(doc_copy)
	
	print(f"Step 5 완료: 제목 추가 ({len(final_docs)}개)")

	# 최종 결과 저장
	with open(output_file_path, 'w', encoding='utf-8') as f:
		json.dump(final_docs, f, ensure_ascii=False, indent=2)

	print(f"✅ 전처리 완료: {output_file_path}")
	print(f"📝 picture 데이터 제거됨, text/table 데이터만 보존")
	
	# 최종 결과 분석
	analyze_final_results(final_docs)
	
	return len(final_docs)


def main():
	import os
	import glob
	
	print(f"=== 🚀 전처리 파이프라인(페이지 텍스트 청킹) 시작 ===")
	
	# 입력 디렉토리 확인
	if not os.path.exists(INPUT_DIR):
		print(f"❌ 입력 디렉토리가 존재하지 않습니다: {INPUT_DIR}")
		return
	
	# 출력 디렉토리 생성 (비우지 않음)
	if not os.path.exists(OUTPUT_DIR):
		print(f"📁 출력 디렉토리 생성: {OUTPUT_DIR}")
		os.makedirs(OUTPUT_DIR)
	
	# datas 폴더의 모든 JSON 파일 찾기 (이미 '凸'로 시작하는 파일은 제외)
	input_files_all = glob.glob(os.path.join(INPUT_DIR, "*.json"))
	input_files = [f for f in input_files_all if not os.path.basename(f).startswith('凸')]
	
	if not input_files:
		print(f"❌ {INPUT_DIR} 폴더에 처리할 JSON 파일이 없습니다. (이미 '凸' 처리된 파일만 존재)")
		return
	
	print(f"📂 처리할 파일 수: {len(input_files)}개")
	
	total_processed = 0
	doc_metadata_no_toc = None
	
	for idx, input_file_path in enumerate(input_files):
		# 파일명에서 확장자 제거
		base_name = os.path.splitext(os.path.basename(input_file_path))[0]
		output_file_name = f"{base_name}_preprocessed.json"
		output_file_path = os.path.join(OUTPUT_DIR, output_file_name)
		
		# 첫 번째 처리 파일에서 metadata 추출
		if doc_metadata_no_toc is None:
			with open(input_file_path, 'r', encoding='utf-8') as f:
				data = json.load(f)
			doc_metadata = data.get('metadata', {})
			doc_metadata_no_toc = {k: v for k, v in doc_metadata.items() if k != 'toc'}
		
		# 파일 전처리
		processed_count = process_single_file(input_file_path, output_file_path, doc_metadata_no_toc)
		total_processed += processed_count
		
		# 원본 입력 파일에 '凸' 접두사 부여하여 재처리 방지
		try:
			src_dir = os.path.dirname(input_file_path)
			src_base = os.path.basename(input_file_path)
			if not src_base.startswith('凸'):
				new_src_path = os.path.join(src_dir, f"凸{src_base}")
				os.rename(input_file_path, new_src_path)
				print(f"🔒 재처리 방지: {src_base} → 凸{src_base}")
		except Exception as e:
			print(f"⚠️ 입력 파일 이름 변경 실패: {input_file_path} ({e})")
	
	print(f"\n🎉 모든 파일 전처리 완료!")
	print(f"📊 총 {len(input_files)}개 파일 처리됨")
	print(f"📈 총 {total_processed}개 문서 생성됨")
	print(f"📁 결과 저장 위치: {OUTPUT_DIR}/")


if __name__ == "__main__":
	main() 